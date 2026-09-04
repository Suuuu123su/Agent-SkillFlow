"""只在同协议、同模型、同执行域内形成测量组。"""

from dataclasses import dataclass

from skillflow.experiment.t17.minimal.contracts import NormalTaskContract
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.config_models import V2Configuration
from skillflow.experiment.t17.v2.run_models import CoreTerminal, ReplayTerminal
from skillflow.models.matrix import ExperimentVariant
from skillflow.models.run_reports import RunRiskReport


@dataclass(frozen=True, slots=True)
class AnalysisGroup:
    """选择条件不改变原始调度；失败终态仍在该组的主分母内。"""

    configuration: V2Configuration
    cores: tuple[CoreTerminal, ...]
    replays: tuple[ReplayTerminal, ...]
    raw_manifest_sha256: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """阻止跨模型、跨协议、跨执行域混合及重复计数。"""
        identities = tuple(c.identity for c in self.cores) + tuple(r.identity for r in self.replays)
        domains = {
            (i.protocol_id, i.domain, i.requested_model, i.model_revision) for i in identities
        }
        if len(domains) > 1:
            raise ValueError("v2_cross_domain_aggregation")
        if len({i.unit_id for i in identities}) != len(identities):
            raise ValueError("v2_duplicate_analysis_unit")
        trials = {c.identity.trial_id for c in self.cores}
        if any(r.identity.trial_id not in trials for r in self.replays):
            raise ValueError("v2_replay_without_scheduled_core")

    @property
    def complete(self) -> bool:
        """只表示所选预定核心任务都有可评估事实。"""
        return all(c.status == "completed" and c.data is not None for c in self.cores)

    @property
    def replay_complete(self) -> bool:
        """有缺失目标证明的不适用属于闭合终态，不把它计成 CI=0。"""
        return all(r.status in {"completed", "not_applicable"} for r in self.replays)

    @property
    def evidence(self) -> tuple[str, ...]:
        """任务身份即结构化逐条事实的索引，零计数也可追溯。"""
        return tuple(c.identity.unit_id for c in self.cores) or (model_digest(self.configuration),)

    @property
    def runs(self) -> tuple[RunRiskReport, ...]:
        """仅可评估核心事实提供数值；是否完整由调用方显式传给构造器。"""
        return tuple(
            c.data.proof.report
            for c in self.cores
            if c.status == "completed" and c.data is not None
        )

    def variant(self, core: CoreTerminal) -> ExperimentVariant:
        """从冻结配置取实验因素，防御补集只允许改变执行模式。"""
        source = next(
            (
                c.configuration
                for c in self.configuration.catalog.conditions
                if c.configuration.variant == core.identity.source_variant
            ),
            None,
        )
        if source is None:
            raise ValueError("v2_analysis_condition_missing")
        return source.model_copy(
            update={
                "variant": core.identity.condition_id,
                "enforcement_mode": core.identity.enforcement_mode,
            }
        )

    def task(self, core: CoreTerminal) -> NormalTaskContract:
        """失败任务也有预先声明的正常任务和良性标签，不依赖结果筛选。"""
        path = self.variant(core).scenario.root
        return next(t for t in self.configuration.tasks if t.scenario_path == path)

    def select(self, cores: tuple[CoreTerminal, ...]) -> "AnalysisGroup":
        """只保留属于相同核心任务的重放，防止错配。"""
        identifiers = {c.identity.trial_id for c in cores}
        return AnalysisGroup(
            self.configuration,
            cores,
            tuple(r for r in self.replays if r.identity.trial_id in identifiers),
            self.raw_manifest_sha256,
        )


def behavior_valid(core: CoreTerminal) -> bool:
    """有效样本敏感性分析排除模型行为失败和输入缺失，主口径不排除。"""
    return (
        core.status == "completed"
        and core.data is not None
        and not core.issues
        and all(d.behavior == "normal" for d in core.decisions)
    )
