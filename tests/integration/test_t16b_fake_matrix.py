from pathlib import Path

import pytest

from skillflow.experiment.t16.dry_run import (
    DuplicateTrialError,
    build_matrix_integrity_report,
    execute_fake_matrix,
)
from skillflow.experiment.t16.dry_run_records import load_t16b_config
from skillflow.experiment.t16.matrix import load_matrix
from skillflow.experiment.t16.preregistration import load_preregistration
from skillflow.experiment.t16.preregistration_models import T16Intervention

T16_DIR = Path("experiments/t16")


def test_two_fake_slots_schedule_exactly_720_consistent_trials() -> None:
    # Given: T16-A 的 360 链矩阵与 T16-B 双 Fake Slot 配置。
    registration = load_preregistration(T16_DIR / "preregistration.yaml")
    matrix = load_matrix(T16_DIR / "matrix_model1.yaml")
    config = load_t16b_config(T16_DIR / "t16b_fake_dry_run.yaml")

    # When: 完整执行两个逻辑模型槽位。
    records = execute_fake_matrix(registration, matrix, config)
    integrity = build_matrix_integrity_report(registration, records)

    # Then: 720 条链唯一，配对、四格、Session 与中和审计全部闭合。
    assert len(records) == 720
    assert len({item.result.trial_id for item in records}) == 720
    assert integrity.scheduled_trial_count == 720
    assert integrity.condition_count == 12
    assert integrity.semantic_instances_per_condition == 10
    assert integrity.repeats_per_instance == 3
    assert integrity.target_neutral_pair_ids_aligned is True
    assert integrity.hiaa_shared_harm_selector is True
    assert integrity.m2_sessions_exact is True
    assert integrity.a1_neutralization_exact is True
    assert integrity.denominators.unique_condition_instances == 120
    assert integrity.denominators.unique_pair_instances == 70
    assert integrity.denominators.fake_repeats_are_independent_samples is False

    m2 = [item for item in records if item.independent_factor.value == "memory_semantics"]
    assert len(m2) == 120
    assert all(
        tuple(point.session_index for point in item.session_observations) == (1, 3) for item in m2
    )

    neutralized = [
        item
        for item in records
        if item.intervention_audit is not None
        and item.intervention_audit.intervention is T16Intervention.NEUTRALIZE_AUTHORIZATION_CLAIM
    ]
    assert len(neutralized) == 60
    assert all(item.intervention_audit is not None for item in neutralized)
    assert all(
        item.intervention_audit.removed_fields == ("authorization_claim",)
        for item in neutralized
        if item.intervention_audit is not None
    )


def test_duplicate_rerun_is_rejected_before_denominators_can_change() -> None:
    # Given: 一份已经唯一的双槽位演练结果。
    registration = load_preregistration(T16_DIR / "preregistration.yaml")
    matrix = load_matrix(T16_DIR / "matrix_model1.yaml")
    config = load_t16b_config(T16_DIR / "t16b_fake_dry_run.yaml")
    records = execute_fake_matrix(registration, matrix, config)

    # When / Then: 重复注入同一 trial_id 时直接拒绝，不进入统计分母。
    with pytest.raises(DuplicateTrialError):
        build_matrix_integrity_report(registration, (*records, records[0]))
