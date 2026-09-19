"""Versioned, value-independent nine-channel evidence projection and transport.

This module does not import SkillFlow, predictors, or oracles. The historical
P4 schema has an explicitly wider public boundary than new sandbox documents.
Only public input projection is an isolation claim; no filesystem ACL is added.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Iterable

CONTRACT = json.loads(Path(__file__).with_name("dependency_contract.json").read_text("utf-8"))
VERSION = CONTRACT["version"]
CHANNELS = tuple(CONTRACT["channels"])
_CHANNEL_SET = frozenset(CHANNELS)
_PUBLIC_KEYS = frozenset(CONTRACT["public_root_keys"])
_EVALUATION_KEYS = frozenset(CONTRACT["evaluation_only_keys"])
_FAILURE_KEYS = frozenset({"qualification", "qualification_evidence", "qualification_complete",
                           "observation_complete", "collector_complete", "execution_complete",
                           "schema_valid"})
_SCOPE_KEYS = frozenset({"scope", "lifetime", "valid_from", "expires_at"})


def canonical_bytes(value: Any) -> bytes:
    """Use the frozen UTF-8 encoding for both payload and control metadata."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _channels(channels: Iterable[str]) -> frozenset[str]:
    channels = frozenset(channels)
    unknown = channels - _CHANNEL_SET
    if unknown:
        raise ValueError("Unknown evidence channels: " + ", ".join(sorted(unknown)))
    return channels


def _pointer(path: tuple[str, ...]) -> str:
    return "/" + "/".join(p.replace("~", "~0").replace("/", "~1") for p in path)


def _path(pointer: str) -> tuple[str, ...]:
    return tuple(p.replace("~1", "/").replace("~0", "~") for p in pointer[1:].split("/"))


def _rule(path: tuple[str, ...], owner: str | None, requires: frozenset[str]
          ) -> tuple[str | None, frozenset[str], str]:
    key = path[-1]
    rule = "inherited"
    if key in _CHANNEL_SET:
        owner, requires, rule = key, requires | {key}, "channel"
    if key == "source_object":
        owner, requires, rule = "provenance", requires | {"provenance"}, "provenance-source"
    elif key in _FAILURE_KEYS:
        owner, requires, rule = "failure", requires | {"failure"}, "failure-qualification"
    elif key in {"grant_limits", "limits"} and "scope_lifetime" in path:
        owner, requires, rule = "scope_lifetime", requires | {"grant", "scope_lifetime"}, "grant-limits"
    elif key in {"grant_issue_positions", "grant_boundary_sessions", "grant_times", "revocations"} and "lifecycle" in path:
        owner, requires, rule = "lifecycle", requires | {"grant", "lifecycle"}, "grant-lifecycle"
    elif key in {"artifact_hashes", "before_sha256", "after_sha256", "artifact_sha256"} and requires:
        owner, requires, rule = "task_success_evidence", requires | {"task_success_evidence"}, "artifact-hash-mirror"
    elif key == "session_id" and requires:
        owner, requires, rule = "lifecycle", requires | {"lifecycle"}, "session-mirror"
    elif key in _SCOPE_KEYS and (requires or "manifest" in path):
        owner, requires, rule = "scope_lifetime", requires | {"scope_lifetime"}, "scope-mirror"
    elif key in {"initial", "unknown_initial_atoms"} and "declared_capability_rules" in path:
        owner, requires, rule = "grant", requires | {"grant"}, "capability-grant-state"
    return owner, frozenset(requires), rule


def _validate_root(document: Any) -> None:
    if not isinstance(document, dict):
        raise TypeError("Evidence document must be a JSON object")
    unknown = set(document) - _PUBLIC_KEYS - _CHANNEL_SET - _EVALUATION_KEYS
    if unknown:
        raise ValueError("Unregistered public root keys: " + ", ".join(sorted(unknown)))


def project(document: dict[str, Any], visible_channels: Iterable[str]) -> dict[str, Any]:
    """Return permitted evidence, masking before inspecting any hidden value.

    Projection is idempotent and deletions commute. Restoration must use a fresh
    source document plus a charged bundle; this function never restores nulls.
    Container cardinality is public only once all container prerequisites are
    available. Optional mirror-key presence follows the frozen input schema;
    masks hide values, not arbitrary undocumented schema changes.
    """
    _validate_root(document)
    visible = _channels(visible_channels)

    def visit(value: Any, path: tuple[str, ...], owner: str | None,
              requires: frozenset[str]) -> Any:
        if path:
            owner, requires, _ = _rule(path, owner, requires)
        if not requires <= visible:
            return None
        if isinstance(value, dict):
            return {key: visit(child, path + (key,), owner, requires)
                    for key, child in value.items() if key not in _EVALUATION_KEYS}
        if isinstance(value, list):
            return [visit(child, path + (str(index),), owner, requires)
                    for index, child in enumerate(value)]
        return copy.deepcopy(value)

    return visit(document, (), None, frozenset())


def build_ledger(document: dict[str, Any]) -> dict[str, Any]:
    """Enumerate every controlled concrete path, including physical mirrors.

    This ledger is evaluation/broker metadata. Its hidden path cardinalities
    must not be passed to a policy as free public information.
    """
    _validate_root(document)
    entries: list[dict[str, Any]] = []

    def visit(value: Any, path: tuple[str, ...], owner: str | None,
              requires: frozenset[str]) -> None:
        rule = "public"
        if path:
            owner, requires, rule = _rule(path, owner, requires)
        if owner is not None:
            pointer = _pointer(path)
            entries.append({"token": VERSION + "#" + pointer, "path": pointer,
                            "owner": owner, "requires": sorted(requires), "rule": rule})
        if isinstance(value, dict):
            for key, child in sorted(value.items()):
                if key not in _EVALUATION_KEYS:
                    visit(child, path + (key,), owner, requires)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, path + (str(index),), owner, requires)

    visit(document, (), None, frozenset())
    return {"contract_version": VERSION, "channels": list(CHANNELS), "entries": entries,
            "owner_coverage": 1.0, "unknown_owner_paths": [],
            "scope": "Registered channel descendants and explicit cross-field paths only",
            "policy_visible": False}


def _diff(before: Any, after: Any, path: tuple[str, ...] = ()) -> list[tuple[str, Any]]:
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict) and before.keys() == after.keys():
        return [patch for key in sorted(after) for patch in _diff(before[key], after[key], path + (key,))]
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [patch for i, value in enumerate(after) for patch in _diff(before[i], value, path + (str(i),))]
    return [(_pointer(path), after)]


def restoration_bundle(document: dict[str, Any], acquired: Iterable[str],
                       requested: Iterable[str] | str) -> dict[str, Any]:
    """Produce one indivisible, chargeable response; do not auto-acquire prerequisites.

    A request grants only the named channel(s). Mirrors are restored when their
    complete prerequisites are acquired; their bytes appear in explicit patches.
    If a parent opens, its transmitted subtree still contains masked descendants.
    """
    before_channels = _channels(acquired)
    requested_channels = _channels([requested] if isinstance(requested, str) else requested)
    after_channels = before_channels | requested_channels
    before, after = project(document, before_channels), project(document, after_channels)
    ledger = build_ledger(document)["entries"]
    by_path = {entry["path"]: entry for entry in ledger}
    patches = []
    for path, value in _diff(before, after):
        entry = by_path.get(path)
        if entry is None:
            raise ValueError("Unregistered restoration path: " + path)
        patches.append({**entry, "value": value})
    atoms = [entry for entry in ledger if set(entry["requires"]) <= after_channels
             and not set(entry["requires"]) <= before_channels]
    return {"contract_version": VERSION, "requested_channels": sorted(requested_channels),
            "acquired_channels": sorted(after_channels), "patches": patches, "atoms": atoms}


def apply_bundle(visible_document: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    """Apply a broker-created bundle after validating its registered dependencies."""
    if bundle.get("contract_version") != VERSION:
        raise ValueError("Dependency contract version mismatch")
    acquired = _channels(bundle["acquired_channels"])
    result = copy.deepcopy(visible_document)
    for patch in bundle["patches"]:
        path = _path(patch["path"])
        owner, requires = None, frozenset()
        for depth in range(1, len(path) + 1):
            owner, requires, _ = _rule(path[:depth], owner, requires)
        if owner != patch["owner"] or sorted(requires) != patch["requires"] or not requires <= acquired:
            raise ValueError("Unregistered or unauthorized restoration")
        if patch["token"] != VERSION + "#" + patch["path"]:
            raise ValueError("Restoration token mismatch")
        parent: Any = result
        for part in path[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        if isinstance(parent, list):
            parent[int(path[-1])] = copy.deepcopy(patch["value"])
        else:
            parent[path[-1]] = copy.deepcopy(patch["value"])
    # A malformed response cannot smuggle a still-hidden nested field via a
    # parent patch. The broker must transmit exactly the permitted projection.
    if project(result, acquired) != result:
        raise ValueError("Bundle contains evidence outside acquired dependency closure")
    return result


def receive_bundle(visible_document: dict[str, Any], bundle: dict[str, Any],
                   charged_total_bytes: int, budget_bytes: int) -> tuple[dict[str, Any], int]:
    """Atomically reject oversize responses; charge all actual response bytes."""
    if charged_total_bytes < 0 or budget_bytes < 0:
        raise ValueError("Byte counts must be nonnegative")
    total = charged_total_bytes + len(canonical_bytes(bundle))
    if total > budget_bytes:
        raise ValueError("BUNDLE_EXCEEDS_REMAINING_BUDGET")
    return apply_bundle(visible_document, bundle), total


def explain_missing(metric: str, protocol: str, acquired: Iterable[str],
                    historical_missing_evidence: Iterable[str] = ()) -> dict[str, Any]:
    """Conservative registered dependencies; never certify old read logs complete."""
    known = _channels(acquired)
    mappings = CONTRACT["metric_protocol_dependencies"]
    required = mappings.get(metric + "/" + protocol, mappings.get(metric + "/*"))
    return {"contract_version": VERSION, "complete": False,
            "reason": "Conservative channel contract; historical nested reads are not a complete proof",
            "registered_metric": required is not None,
            "missing_channels": sorted(set(required or ()) - known),
            "historical_missing_evidence": sorted(historical_missing_evidence)}
