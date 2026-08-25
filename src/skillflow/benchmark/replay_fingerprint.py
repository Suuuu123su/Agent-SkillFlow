"""成对重放共享条件的规范化摘要。"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import JsonValue

from skillflow.adapters.checkpoint import HarnessCheckpoint
from skillflow.benchmark.manifests import ManifestBinding
from skillflow.benchmark.replay_models import ReplayControlEvidence
from skillflow.benchmark.scripted_backend import FixtureScript, ToolScriptAction
from skillflow.models.enums import Decision
from skillflow.models.scenario import Scenario


@dataclass(frozen=True, slots=True)
class ReplayFingerprintSetup:
    """生成共享条件证据所需的可信输入。"""

    scenario: Scenario
    scripts: Mapping[str, FixtureScript]
    decisions: Mapping[str, Decision]
    manifests: tuple[ManifestBinding, ...]
    seed: str
    checkpoint: HarnessCheckpoint


def build_control_evidence(setup: ReplayFingerprintSetup) -> ReplayControlEvidence:
    """只导出摘要，不泄漏 Fixture 输出、参数正文或路径。"""
    return ReplayControlEvidence(
        seed_hash=_hash(setup.seed),
        scripts_hash=_hash(_scripts_payload(setup.scripts)),
        decisions_hash=_hash({key: value.value for key, value in sorted(setup.decisions.items())}),
        manifests_hash=_hash(
            [
                [binding.skill_id, binding.manifest.model_dump(mode="json")]
                for binding in setup.manifests
            ]
        ),
        grants_hash=_hash([grant.model_dump(mode="json") for grant in setup.scenario.grants]),
        clock_start=setup.scenario.clock.start.isoformat(),
        checkpoint_state_hash=setup.checkpoint.state_hash,
    )


def _scripts_payload(scripts: Mapping[str, FixtureScript]) -> list[JsonValue]:
    return [
        {
            "implementation": implementation,
            "output_hash": hashlib.sha256(script.output).hexdigest(),
            "output_length": len(script.output),
            "output_mime_type": script.output_mime_type,
            "actions": [_action_payload(action) for action in script.actions],
        }
        for implementation, script in sorted(scripts.items())
    ]


def _action_payload(action: ToolScriptAction) -> JsonValue:
    binding = action.input_binding
    gate = action.input_gate
    return {
        "action_id": action.action_id,
        "decision_key": action.decision_key,
        "arguments": action.arguments.model_dump(mode="json"),
        "input_binding": None if binding is None else binding.input_index,
        "input_gate": (
            None
            if gate is None
            else {
                "input_index": gate.input_index,
                "expected_content_hash": gate.expected_content_hash,
                "mismatch_decision_key": gate.mismatch_decision_key,
            }
        ),
    }


def _hash(payload: JsonValue) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
