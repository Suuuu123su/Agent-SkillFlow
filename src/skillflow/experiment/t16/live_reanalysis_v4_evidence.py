"""T16-C 0.4 冻结设计、Phase Contract 与下界 Receipt 绑定。"""

from typing import assert_never

from skillflow.experiment.t16.live_reanalysis_models import (
    DesignLabeledOperationalUea,
    TargetExecutionAuthorizationSummary,
)
from skillflow.experiment.t16.live_reanalysis_v3 import LoadedLiveReanalysisDesign
from skillflow.experiment.t16.live_reanalysis_v4_models import (
    DesignLabeledOperationalUeaV4,
    PhaseContractBinding,
    TargetExecutionAuthorizationSummaryV4,
)
from skillflow.experiment.t16.live_records import LiveTrialRecord

PHASE_CONTRACT_V2_MISSING_ERROR = "0.2 Live Record 缺少 phase contract SHA256"
PHASE_CONTRACT_MIXED_ERROR = "phase contract 必须在全部 Trial 中一致且同时可用"
HISTORICAL_PHASE_REASON = "历史 0.1 Live Record 未记录 Phase Contract SHA256"
HISTORICAL_PHASE_LIMITATION = "历史 0.1 Live Record 无法绑定 Phase Contract；该字段结构化报告为 N/A"


class LiveReanalysisV4Error(ValueError):
    """来源、设计或 Phase Contract 无法满足 v0.4 合同。"""

    __slots__ = ("detail",)

    def __init__(self, detail: str) -> None:
        """保留类型化诊断，同时允许 Python 写入异常 traceback。"""
        super().__init__(detail)
        self.detail = detail

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return self.detail


def require_record_design_fields(
    records: tuple[LiveTrialRecord, ...],
    design: LoadedLiveReanalysisDesign,
) -> None:
    """逐条比较 Record、Matrix TrialSpec 与预注册 Condition 的冻结字段。"""
    trials = {item.trial_id: item for item in design.matrix.trials}
    conditions = {item.condition_id: item for item in design.registration.conditions}
    for record in records:
        trial = trials.get(record.matrix_trial_id)
        if trial is None:
            detail = f"{record.result.trial_id}: matrix_trial_id 不在冻结 Matrix"
            raise LiveReanalysisV4Error(detail)
        condition = conditions[trial.condition_id]
        comparisons = (
            ("scenario", record.result.scenario, trial.scenario),
            ("condition_id", record.result.condition_id, trial.condition_id),
            (
                "semantic_instance_id",
                record.result.semantic_instance_id,
                trial.semantic_instance_id,
            ),
            ("pair_id", record.result.pair_id, trial.pair_id),
            ("repeat_index", record.result.repeat_index, trial.repeat_index),
            ("pair_role", record.pair_role, condition.pair_role),
            ("independent_factor", record.independent_factor, condition.independent_factor),
            ("hiaa_cell", record.hiaa_cell, condition.hiaa_cell),
            ("harm_selector", record.harm_selector, condition.harm_selector),
            ("intervention", record.intervention, condition.intervention),
        )
        mismatched = tuple(name for name, actual, expected in comparisons if actual != expected)
        if mismatched:
            fields = ", ".join(mismatched)
            detail = f"{record.result.trial_id}: Record 与冻结设计字段不一致: {fields}"
            raise LiveReanalysisV4Error(detail)


def phase_contract_binding(
    records: tuple[LiveTrialRecord, ...],
) -> tuple[PhaseContractBinding, tuple[str, ...]]:
    """把全部未来记录绑定到一个 hash；历史 0.1 缺失返回结构化 N/A。"""
    historical = tuple(item for item in records if _v1_record(item))
    if historical:
        if len(historical) != len(records):
            raise LiveReanalysisV4Error(PHASE_CONTRACT_MIXED_ERROR)
        unavailable_ids = tuple(item.result.trial_id for item in records)
        return (
            PhaseContractBinding(
                status="not_available",
                reason=HISTORICAL_PHASE_REASON,
                unavailable_trial_ids=unavailable_ids,
            ),
            (HISTORICAL_PHASE_LIMITATION,),
        )
    missing = tuple(item for item in records if item.phase_contract_sha256 is None)
    if missing:
        raise LiveReanalysisV4Error(PHASE_CONTRACT_V2_MISSING_ERROR)
    hashes = {item.phase_contract_sha256 for item in records if item.phase_contract_sha256}
    if len(hashes) != 1:
        raise LiveReanalysisV4Error(PHASE_CONTRACT_MIXED_ERROR)
    return PhaseContractBinding(status="available", sha256=next(iter(hashes))), ()


def _v1_record(record: LiveTrialRecord) -> bool:
    match record.schema_version:
        case "0.1":
            return True
        case "0.2" | "0.3":
            return False
        case unreachable:
            assert_never(unreachable)


def unclassified_receipts(
    records: tuple[LiveTrialRecord, ...],
    trial_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """按 trial_id 顺序选择每条未分类 Trial 的首个原始 Receipt。"""
    by_id = {item.result.trial_id: item for item in records}
    receipts: list[str] = []
    for trial_id in trial_ids:
        record = by_id[trial_id]
        receipt = next(
            (
                call.receipt_id
                for session in record.sessions
                for call in session.tool_calls
                if call.accepted and call.receipt_id is not None
            ),
            None,
        )
        if receipt is None:
            detail = f"{trial_id}: 未分类 receipted Trial 缺少原始 Receipt"
            raise LiveReanalysisV4Error(detail)
        receipts.append(receipt)
    return tuple(receipts)


def target_v4(
    source: TargetExecutionAuthorizationSummary,
    unclassified: tuple[str, ...],
) -> TargetExecutionAuthorizationSummaryV4:
    """把 v0.3 目标执行下界扩展为可由 Receipt 复验的 v0.4 分区。"""
    return TargetExecutionAuthorizationSummaryV4(
        authorization_basis=source.authorization_basis,
        formal_grant_observation_status=source.formal_grant_observation_status,
        target_execution_count=source.target_execution_count,
        structured_authorized_execution_count=source.structured_authorized_execution_count,
        structured_unauthorized_execution_count=source.structured_unauthorized_execution_count,
        target_trial_ids=source.target_trial_ids,
        structured_authorized_trial_ids=source.structured_authorized_trial_ids,
        structured_unauthorized_trial_ids=source.structured_unauthorized_trial_ids,
        receipt_ids=source.receipt_ids,
        evidence_status=source.evidence_status,
        count_semantics=source.count_semantics,
        unclassified_receipted_trial_count=source.unclassified_receipted_trial_count,
        unclassified_receipted_trial_ids=source.unclassified_receipted_trial_ids,
        unclassified_receipt_ids=unclassified,
    )


def operational_v4(
    source: DesignLabeledOperationalUea,
    unclassified: tuple[str, ...],
) -> DesignLabeledOperationalUeaV4:
    """把操作性 UEA 下界扩展为可由 Receipt 复验的 v0.4 分区。"""
    return DesignLabeledOperationalUeaV4(
        authorization_basis=source.authorization_basis,
        unauthorized_executed_count=source.unauthorized_executed_count,
        affected_trial_count=source.affected_trial_count,
        affected_trial_ids=source.affected_trial_ids,
        receipt_ids=source.receipt_ids,
        evidence_status=source.evidence_status,
        count_semantics=source.count_semantics,
        unclassified_receipted_trial_ids=source.unclassified_receipted_trial_ids,
        unclassified_receipt_ids=unclassified,
    )
