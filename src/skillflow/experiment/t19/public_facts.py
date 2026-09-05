"""仅事实的公开交换合同；重新计算时没有原报告数值可读。"""

from pydantic import JsonValue

from skillflow.benchmark.replay_models import ReplayPairManifest
from skillflow.experiment.t17.v2.portable import recompute_core
from skillflow.experiment.t17.v2.portable_models import (
    PortableCore,
    PortableCoreInputs,
    PortableRun,
)
from skillflow.experiment.t17.v2.replay_proof import build_replay_proof
from skillflow.experiment.t17.v2.runtime_models import DecisionFact, ExecutionIssue
from skillflow.experiment.t19.boundaries import BoundaryIssue
from skillflow.experiment.t19.execution import CoreRecord
from skillflow.experiment.t19.matrix import Trial
from skillflow.experiment.t19.metric_adapter import MetricBinding
from skillflow.experiment.t19.recovery import LimitFact, RecoveryFact
from skillflow.experiment.t19.replay import ReplayRecord
from skillflow.models.base import StrictModel
from skillflow.models.scenario_parts import EffectSelector


class PublicCore(StrictModel):
    """事实与执行观测分离；runtime只允许CoreRecord中非data字段。"""

    trial: Trial
    binding: MetricBinding
    inputs: PortableCoreInputs
    runtime: dict[str, JsonValue]

    @classmethod
    def capture(cls, trial: Trial, binding: MetricBinding, core: CoreRecord) -> "PublicCore":
        """删除已计算的proof，保留全部未聚合观测。"""
        return cls(
            trial=trial,
            binding=binding,
            inputs=PortableCoreInputs.model_validate(core.data.model_dump(exclude={"proof"})),
            runtime=core.model_dump(mode="json", exclude={"data"}),
        )

    def rebuild(self) -> CoreRecord:
        """授权、回执、正常任务与来源指标全部从原始事实重算。"""
        if set(self.runtime) != set(CoreRecord.model_fields) - {"data"}:
            raise ValueError("t19_public_runtime_fields")
        result = CoreRecord.model_validate(
            {
                **self.runtime,
                "data": PortableCore(**self.inputs.model_dump(), proof=recompute_core(self.inputs)),
            }
        )
        if (result.unit_id, result.group) != (self.trial.trial_id, self.trial.group):
            raise ValueError("t19_public_trial_binding")
        return result


class ReplayInputs(StrictModel):
    """不包含CI、baseline或y；manifest内的Effect IDs只作事实一致性断言。"""

    source: PortableRun
    original: PortableRun
    neutral: PortableRun
    selector: EffectSelector
    manifest: ReplayPairManifest


class BranchObservation(StrictModel):
    """分支模型行为与运行失败，无私有结果路径。"""

    run_id: str
    decisions: tuple[DecisionFact, ...]
    issues: tuple[ExecutionIssue, ...]
    recoveries: tuple[RecoveryFact, ...]
    limits: tuple[LimitFact, ...]
    boundary_issues: tuple[BoundaryIssue, ...]


class PublicReplay(StrictModel):
    """同视图和分支观测保留，删除原计算结果。"""

    runtime: dict[str, JsonValue]
    inputs: ReplayInputs | None
    observations: tuple[BranchObservation, ...] = ()

    @classmethod
    def capture(cls, replay: ReplayRecord) -> "PublicReplay":
        """逐字段提取事实，不能导出proof中的计算值。"""
        proof = replay.proof
        return cls(
            runtime=replay.model_dump(mode="json", exclude={"proof", "branch_details"}),
            inputs=ReplayInputs(
                source=proof.source,
                original=proof.original,
                neutral=proof.neutral,
                selector=proof.selector,
                manifest=proof.manifest,
            )
            if proof
            else None,
            observations=tuple(
                BranchObservation(
                    run_id=b.result.run_id,
                    decisions=b.decisions,
                    issues=b.issues,
                    recoveries=b.recoveries,
                    limits=b.limits,
                    boundary_issues=b.boundary_issues,
                )
                for b in replay.branch_details
            ),
        )

    def rebuild(self) -> ReplayRecord:
        """缺分支事实不能补成零CI。"""
        if set(self.runtime) != set(ReplayRecord.model_fields) - {"proof", "branch_details"}:
            raise ValueError("t19_public_replay_fields")
        p = self.inputs
        return ReplayRecord.model_validate(
            {
                **self.runtime,
                "proof": build_replay_proof(p.source, p.original, p.neutral, p.selector, p.manifest)
                if p
                else None,
            }
        )
