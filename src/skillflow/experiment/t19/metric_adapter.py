"""T19 事实适配到既有严格 ALR/RIR 输入，不引入旧实验样本。"""

import hashlib
import json
from dataclasses import dataclass

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.canonical import canonical_digest, model_digest
from skillflow.experiment.t17.v2.run_models import CoreTerminal, ReplayTerminal, UnitIdentity
from skillflow.experiment.t18.catalog_models import LocalSkill
from skillflow.experiment.t19.execution import CoreRecord
from skillflow.experiment.t19.matrix import Trial
from skillflow.experiment.t19.replay import ReplayRecord
from skillflow.models.base import StrictModel
from skillflow.models.enums import EnforcementMode


class MetricBinding(StrictModel):
    """冻结内容的真实摘要，不能以标签或全零占位符代替。"""

    skill_variant_id: str
    skill_content_sha256: str
    manifest_sha256: str
    task_contract_id: str
    task_contract_sha256: str
    source_control_hashes: tuple[str, ...] = ()


def bind_skill(skill: LocalSkill) -> MetricBinding:
    """只散列当前实际采用的任务和技能包。"""
    return MetricBinding(
        source_control_hashes=_control_hashes(skill),
        skill_variant_id=skill.skill_variant_id,
        skill_content_sha256=model_digest(skill.bundle),
        manifest_sha256=canonical_digest(skill.manifests),
        task_contract_id=skill.task_contract.task_id,
        task_contract_sha256=model_digest(skill.task_contract),
    )


@dataclass(frozen=True, slots=True)
class MetricContext:
    """阶段和矩阵摘要来自实际冻结合同。"""

    phase_sha256: str
    matrix_sha256: str


def adapt_core(
    context: MetricContext, trial: Trial, core: CoreRecord, binding: MetricBinding
) -> CoreTerminal:
    """旧 stage 枚举仅用作公式兼容槽，T19阶段身份仍在外部Trial和phase摘要。"""
    identity = UnitIdentity(
        protocol_id="t19-rx-v1",
        stage=T17LiveStage.DEFENSE,
        domain=core.domain,
        phase_contract_sha256=context.phase_sha256,
        matrix_sha256=context.matrix_sha256,
        unit_id=core.unit_id,
        trial_id=trial.trial_id,
        condition_id=":".join(
            (trial.mechanism, trial.template, trial.role, str(trial.bridge), trial.group)
        ),
        source_variant=binding.skill_variant_id,
        skill_variant_id=binding.skill_variant_id,
        skill_content_sha256=binding.skill_content_sha256,
        manifest_sha256=binding.manifest_sha256,
        task_contract_id=binding.task_contract_id,
        task_contract_sha256=binding.task_contract_sha256,
        semantic_template_id=trial.template,
        semantic_instance_id=trial.template,
        repeat_index=trial.repeat,
        defense_base_id=canonical_digest(
            (trial.mechanism, trial.template, trial.role, trial.bridge)
        ),
        enforcement_mode=EnforcementMode.MONITOR
        if trial.group == "Monitor"
        else EnforcementMode.ENFORCE,
        requested_model="deepseek-v4-flash" if core.domain == "live_reference" else core.domain,
        model_revision="deepseek-v4-flash" if core.domain == "live_reference" else core.domain,
    )
    return CoreTerminal(
        identity=identity,
        status="completed",
        run_id=core.unit_id,
        data=core.data,
        decisions=core.decisions,
        issues=core.issues,
        usage=core.usage,
        wall_latency_ms=core.latency_ms,
    )


def adapt_replay(core: CoreTerminal, replay: ReplayRecord) -> ReplayTerminal:
    """严格公式只使用同源核心与重放事实；不把缺失重放伪装CI=0。"""
    if replay.source_unit_id != core.run_id:
        raise ValueError("t19_metric_replay_source_mismatch")
    return ReplayTerminal(
        identity=core.identity.model_copy(update={"unit_id": replay.pair_id}),
        source_core_run_id=core.run_id,
        target_alias=replay.target_alias,
        status=replay.status,
        reason=None if replay.status == "completed" else replay.reason,
        proof=replay.proof,
        absent_source=replay.absent_source,
    )


def _control_hashes(skill: LocalSkill) -> tuple[str, ...]:
    """只散列冻结facts/control来源，便于确认实际污染写入集合。"""
    values = [script.output for script in skill.bundle.scripts.values()]
    values.extend(a.marker.encode() for a in skill.scenario.assets if a.marker is not None)
    hashes = set()
    for payload in values:
        try:
            value = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            continue
        if (
            isinstance(value, dict)
            and isinstance(value.get("facts"), dict)
            and isinstance(value.get("control"), str)
        ):
            hashes.add(hashlib.sha256(payload).hexdigest())
    return tuple(sorted(hashes))
