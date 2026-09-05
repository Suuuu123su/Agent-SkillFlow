"""受信导出器对实际源的结构检查；正文仍留在私有检查点。"""

import hashlib
import json
from contextlib import suppress
from pathlib import Path

from skillflow.experiment.t17.v2.canonical import canonical_digest
from skillflow.experiment.t19.neutralization import neutralize_control
from skillflow.experiment.t19.persistence import PrivateReplaySource
from skillflow.experiment.t19.public_facts import PublicCore, PublicReplay
from skillflow.experiment.t19.replay import ReplayRecord
from skillflow.models.base import StrictModel


class SourceCertificate(StrictModel):
    """结构属性是受信检查器的观测，不是假装公开了私有正文。"""

    pair_id: str
    source_unit_id: str
    target_alias: str
    produced: bool
    source_artifact_id: str | None = None
    source_sha256: str | None = None
    content_length: int | None = None
    separable: bool
    neutral_sha256: str | None = None
    facts_sha256: str | None = None
    source_prefix_steps: int
    contract: str = "t19-facts-control-v1"
    observation_scope: str = "trusted_exporter_inspected_private_source_with_public_hash_binding"


class SourceCertificates(StrictModel):
    """每个实际候选一项，包括源未产生的封闭失败。"""

    items: tuple[SourceCertificate, ...]


def collect(campaign: Path, pairs: tuple[PublicReplay, ...]) -> SourceCertificates:
    """只读既有检查点，不执行重放、模型或SafeSink动作。"""
    items = []
    for public in pairs:
        replay = public.rebuild()
        path = campaign / "checkpoints" / replay.source_unit_id / (replay.target_alias + ".json")
        if not path.exists():
            items.append(
                SourceCertificate(
                    pair_id=replay.pair_id,
                    source_unit_id=replay.source_unit_id,
                    target_alias=replay.target_alias,
                    produced=False,
                    separable=False,
                    source_prefix_steps=0,
                )
            )
            continue
        saved = PrivateReplaySource.model_validate_json(path.read_text(encoding="utf-8"))
        source = saved.source()
        artifact = next(
            a
            for a in source.checkpoint.store.artifacts
            if a.artifact.artifact_id == source.source_artifact_id
        )
        content = artifact.content
        neutral = None
        facts_hash = None
        with suppress(ValueError, TypeError):
            neutral = neutralize_control(content)
        if neutral is not None:
            before, after = json.loads(content), json.loads(neutral)
            if before["facts"] != after["facts"] or len(content) != len(neutral):
                raise ValueError("t19_source_certificate_fact_drift")
            facts_hash = canonical_digest(before["facts"])
        items.append(
            SourceCertificate(
                pair_id=replay.pair_id,
                source_unit_id=replay.source_unit_id,
                target_alias=replay.target_alias,
                produced=True,
                source_artifact_id=source.source_artifact_id,
                source_sha256=hashlib.sha256(content).hexdigest(),
                content_length=len(content),
                separable=neutral is not None,
                neutral_sha256=hashlib.sha256(neutral).hexdigest() if neutral is not None else None,
                facts_sha256=facts_hash,
                source_prefix_steps=saved.prefix_steps,
            )
        )
    return SourceCertificates(items=tuple(items))


def validate_sources(
    cores: tuple[PublicCore, ...], pairs: tuple[PublicReplay, ...], certificates: SourceCertificates
) -> tuple[str, ...]:
    """公开事实核查证书来源与分支哈希；结构观测依赖受信检查器。"""
    core_map = {c.trial.trial_id: c for c in cores}
    certs = {c.pair_id: c for c in certificates.items}
    failures = []
    if len(certs) != len(certificates.items) or set(certs) != {p.rebuild().pair_id for p in pairs}:
        failures.append("certificate_candidate_coverage")
    for public in pairs:
        replay = public.rebuild()
        cert, core = certs.get(replay.pair_id), core_map.get(replay.source_unit_id)
        if cert is None or core is None:
            failures.append(replay.pair_id + ":missing_source_binding")
            continue
        failures.extend(_source_binding(core, cert, replay))
        failures.extend(_branch_binding(cert, replay))
    return tuple(failures)


def _source_binding(
    core: PublicCore, cert: SourceCertificate, replay: ReplayRecord
) -> tuple[str, ...]:
    """源别名、字节哈希和前缀计步一致。"""
    failures = []
    actual = core.inputs.artifact_ids_by_alias.get(replay.target_alias)
    if actual != cert.source_artifact_id or cert.produced != (actual is not None):
        failures.append(replay.pair_id + ":source_alias_mismatch")
    if replay.source_prefix_steps != cert.source_prefix_steps:
        failures.append(replay.pair_id + ":prefix_step_mismatch")
    if cert.produced:
        artifact = next((a for a in core.inputs.facts.artifacts if a.artifact_id == actual), None)
        if artifact is None or (artifact.content_hash, artifact.content_length) != (
            cert.source_sha256,
            cert.content_length,
        ):
            failures.append(replay.pair_id + ":source_content_binding")
    return tuple(failures)


def _branch_binding(cert: SourceCertificate, replay: ReplayRecord) -> tuple[str, ...]:
    """中和和原视图绑定实际源，不能把可分离源声明为N/A。"""
    failures = []
    if replay.proof is not None:
        proof = replay.proof
        expected = (
            (
                proof.original,
                proof.manifest.original_intervention.derived_artifact_id,
                cert.source_sha256,
            ),
            (
                proof.neutral,
                proof.manifest.neutral_intervention.derived_artifact_id,
                cert.neutral_sha256,
            ),
        )
        if not cert.separable:
            failures.append(replay.pair_id + ":invalid_claim_of_neutralization")
        for branch, derived_id, content_hash in expected:
            derived = next((a for a in branch.artifacts if a.artifact_id == derived_id), None)
            if derived is None or derived.content_hash != content_hash:
                failures.append(replay.pair_id + ":branch_content_binding")
    elif replay.reason == "target_not_produced_in_closed_core" and cert.produced:
        failures.append(replay.pair_id + ":false_source_absence")
    elif replay.reason == "source_generation_outside_frozen_control_envelope" and cert.separable:
        failures.append(replay.pair_id + ":false_inapplicability")
    return tuple(failures)
