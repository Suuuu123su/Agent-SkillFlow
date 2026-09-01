"""T16-B 720 链 Matrix 的机械完整性检查。"""

from dataclasses import dataclass

from skillflow.experiment.t16.dry_run_errors import DryRunDesignError, DryRunDesignReason
from skillflow.experiment.t16.dry_run_failures import operational_disposition
from skillflow.experiment.t16.dry_run_records import (
    A1_PRESERVED_FIELDS,
    DryRunTrialRecord,
)
from skillflow.experiment.t16.dry_run_reports import (
    DuplicateHandling,
    MatrixIntegrityReport,
    OperationalCounts,
    OperationalDisposition,
    StatisticalDenominators,
)
from skillflow.experiment.t16.preregistration_models import (
    IndependentFactor,
    PairRole,
    T16Condition,
    T16Intervention,
    T16Preregistration,
)


@dataclass(frozen=True, slots=True)
class DuplicateTrialError(ValueError):
    """重复运行身份在进入分母前被拒绝。"""

    trial_id: str

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return f"重复 trial_id: {self.trial_id}"


def build_matrix_integrity_report(
    registration: T16Preregistration,
    records: tuple[DryRunTrialRecord, ...],
) -> MatrixIntegrityReport:
    """检查运行数、配对、四格、M2、A1 与去重分母。"""
    _reject_duplicate_trials(records)
    expected = registration.primary_trial_count * 2
    if len(records) != expected:
        detail = f"expected={expected}, actual={len(records)}"
        raise DryRunDesignError(DryRunDesignReason.WRONG_TRIAL_COUNT, detail)
    conditions = {item.condition_id: item for item in registration.conditions}
    _require_instance_counts(registration, records, conditions)
    return MatrixIntegrityReport(
        expected_trial_count=expected,
        scheduled_trial_count=len(records),
        unique_trial_id_count=len({item.result.trial_id for item in records}),
        slot_count=len({item.slot_id for item in records}),
        condition_count=len(conditions),
        semantic_instances_per_condition=registration.semantic_instances_per_condition,
        repeats_per_instance=registration.repeats_per_instance,
        target_neutral_pair_ids_aligned=_pair_ids_aligned(records, conditions),
        hiaa_shared_harm_selector=_hiaa_selector_aligned(records, conditions),
        m2_sessions_exact=_m2_sessions_exact(records),
        a1_neutralization_exact=_a1_neutralization_exact(records, conditions),
        duplicate_handling=DuplicateHandling.REJECT,
        denominators=StatisticalDenominators(
            unique_condition_instances=len(
                {(item.result.condition_id, item.result.semantic_instance_id) for item in records}
            ),
            unique_pair_instances=len({item.result.pair_id for item in records}),
        ),
        operational_counts=_operational_counts(records),
    )


def _require_instance_counts(
    registration: T16Preregistration,
    records: tuple[DryRunTrialRecord, ...],
    conditions: dict[str, T16Condition],
) -> None:
    counts = {
        condition_id: len(
            {
                item.result.semantic_instance_id
                for item in records
                if item.result.condition_id == condition_id
            }
        )
        for condition_id in conditions
    }
    if set(counts.values()) != {registration.semantic_instances_per_condition}:
        raise DryRunDesignError(DryRunDesignReason.WRONG_INSTANCE_COUNT)


def _reject_duplicate_trials(records: tuple[DryRunTrialRecord, ...]) -> None:
    seen: set[str] = set()
    for record in records:
        trial_id = record.result.trial_id
        if trial_id in seen:
            raise DuplicateTrialError(trial_id)
        seen.add(trial_id)


def _pair_ids_aligned(
    records: tuple[DryRunTrialRecord, ...],
    conditions: dict[str, T16Condition],
) -> bool:
    buckets: dict[tuple[str, str, str, int], set[str]] = {}
    for record in records:
        condition = conditions[record.result.condition_id]
        key = (
            record.slot_id,
            condition.pair_group_id,
            record.result.semantic_instance_id,
            record.result.repeat_index,
        )
        buckets.setdefault(key, set()).add(record.result.pair_id)
    return all(len(pair_ids) == 1 for pair_ids in buckets.values())


def _hiaa_selector_aligned(
    records: tuple[DryRunTrialRecord, ...],
    conditions: dict[str, T16Condition],
) -> bool:
    designs: dict[str, set[str]] = {}
    for record in records:
        condition = conditions[record.result.condition_id]
        if condition.hiaa_design_id is None or record.harm_selector is None:
            continue
        designs.setdefault(condition.hiaa_design_id, set()).add(record.harm_selector.root)
    return bool(designs) and all(len(selectors) == 1 for selectors in designs.values())


def _m2_sessions_exact(records: tuple[DryRunTrialRecord, ...]) -> bool:
    memory_records = [
        item for item in records if item.independent_factor is IndependentFactor.MEMORY_SEMANTICS
    ]
    return bool(memory_records) and all(
        tuple(point.session_index for point in item.session_observations) == (1, 3)
        for item in memory_records
    )


def _a1_neutralization_exact(
    records: tuple[DryRunTrialRecord, ...],
    conditions: dict[str, T16Condition],
) -> bool:
    expected_records = [
        item
        for item in records
        if conditions[item.result.condition_id].intervention
        is T16Intervention.NEUTRALIZE_AUTHORIZATION_CLAIM
    ]
    neutral_conditions = [
        item
        for item in conditions.values()
        if item.intervention is T16Intervention.NEUTRALIZE_AUTHORIZATION_CLAIM
    ]
    if len(neutral_conditions) != 1:
        return False
    neutral = neutral_conditions[0]
    targets = [
        item
        for item in conditions.values()
        if item.pair_group_id == neutral.pair_group_id and item.pair_role is PairRole.TARGET
    ]
    if len(targets) != 1:
        return False
    target = targets[0]
    controls_unchanged = (
        neutral.scenario == target.scenario
        and neutral.instance_set_id == target.instance_set_id
        and neutral.capability == target.capability
    )
    audits_exact = bool(expected_records) and all(
        item.intervention_audit is not None
        and item.intervention_audit.removed_fields == ("authorization_claim",)
        and item.intervention_audit.preserved_fields == A1_PRESERVED_FIELDS
        for item in expected_records
    )
    return controls_unchanged and audits_exact


def _operational_counts(records: tuple[DryRunTrialRecord, ...]) -> OperationalCounts:
    dispositions = tuple(operational_disposition(item.result) for item in records)
    return OperationalCounts(
        harm=dispositions.count(OperationalDisposition.HARM),
        completed_without_harm=dispositions.count(OperationalDisposition.COMPLETED_WITHOUT_HARM),
        refusal=dispositions.count(OperationalDisposition.REFUSAL),
        no_call=dispositions.count(OperationalDisposition.NO_CALL),
        invalid_other=dispositions.count(OperationalDisposition.INVALID_OTHER),
    )
