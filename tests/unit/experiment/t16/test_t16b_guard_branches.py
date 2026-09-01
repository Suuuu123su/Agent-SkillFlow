from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import ValidationError

from skillflow.experiment.t16.dry_run import (
    build_matrix_integrity_report,
    execute_fake_matrix,
)
from skillflow.experiment.t16.dry_run_checks import (
    FailureInjectionKind,
    operational_disposition,
    verify_network_probe_is_blocked,
)
from skillflow.experiment.t16.dry_run_costs import build_cost_simulation_report
from skillflow.experiment.t16.dry_run_errors import (
    DryRunDesignError,
    FailureRehearsalError,
)
from skillflow.experiment.t16.dry_run_failures import verify_budget_limit
from skillflow.experiment.t16.dry_run_io import (
    DryRunOutputError,
    DryRunResultStore,
    DuplicateStoredTrialError,
    read_trial_records,
    sha256_path,
    write_json_model,
)
from skillflow.experiment.t16.dry_run_records import (
    A1_PRESERVED_FIELDS,
    DryRunInterventionAudit,
    DryRunTrialRecord,
    SessionEffectObservation,
    T16BDryRunConfig,
    load_t16b_config,
)
from skillflow.experiment.t16.matrix import T16Matrix, load_matrix
from skillflow.experiment.t16.preregistration import load_preregistration
from skillflow.experiment.t16.preregistration_models import (
    T16Intervention,
    T16Preregistration,
)
from skillflow.experiment.t16.trial import TrialOutcome, TrialResult

T16_DIR = Path("experiments/t16")


@dataclass(frozen=True, slots=True)
class DryRunFixture:
    registration: T16Preregistration
    matrix: T16Matrix
    config: T16BDryRunConfig
    records: tuple[DryRunTrialRecord, ...]


@pytest.fixture(scope="module")
def dry_run_fixture() -> DryRunFixture:
    registration = load_preregistration(T16_DIR / "preregistration.yaml")
    matrix = load_matrix(T16_DIR / "matrix_model1.yaml")
    config = load_t16b_config(T16_DIR / "t16b_fake_dry_run.yaml")
    return DryRunFixture(
        registration=registration,
        matrix=matrix,
        config=config,
        records=execute_fake_matrix(registration, matrix, config),
    )


def test_result_store_rejects_duplicates_and_wraps_io_errors(
    dry_run_fixture: DryRunFixture,
    tmp_path: Path,
) -> None:
    # Given: 一个已初始化的逐条 flush Store。
    path = tmp_path / "records.jsonl"
    store = DryRunResultStore(path)
    store.initialize()
    store.append(dry_run_fixture.records[0])

    # When / Then: 重复落盘和已有输出均被结构化拒绝。
    with pytest.raises(DuplicateStoredTrialError) as duplicate:
        store.append(dry_run_fixture.records[0])
    assert "重复 trial_id" in str(duplicate.value)
    with pytest.raises(DryRunOutputError) as existing:
        write_json_model(path, dry_run_fixture.records[0])
    assert path.name in str(existing.value)

    missing = tmp_path / "missing.jsonl"
    with pytest.raises(DryRunOutputError):
        read_trial_records(missing)
    with pytest.raises(DryRunOutputError):
        sha256_path(missing)


def test_record_models_reject_inconsistent_session_intervention_and_identity(
    dry_run_fixture: DryRunFixture,
) -> None:
    # Given / When / Then: Session 执行必须同时有 request 与 Receipt。
    with pytest.raises(ValidationError):
        SessionEffectObservation(
            session_index=1,
            target_effect_requested=True,
            target_effect_executed=True,
        )
    with pytest.raises(ValidationError):
        SessionEffectObservation(
            session_index=1,
            target_effect_requested=False,
            target_effect_executed=True,
            receipt_id="receipt-invalid",
        )

    # Given / When / Then: 未注册删除和不完整能力保持证据均拒绝。
    with pytest.raises(ValidationError):
        DryRunInterventionAudit(
            intervention=T16Intervention.NONE,
            removed_fields=("authorization_claim",),
            preserved_fields=(),
        )
    with pytest.raises(ValidationError):
        DryRunInterventionAudit(
            intervention=T16Intervention.NEUTRALIZE_AUTHORIZATION_CLAIM,
            removed_fields=("authorization_claim",),
            preserved_fields=A1_PRESERVED_FIELDS[:-1],
        )

    # Given / When / Then: 槽位身份、HIAA 绑定和 Session 顺序不能漂移。
    record = dry_run_fixture.records[0]
    payload = record.model_dump(mode="python")
    payload["matrix_trial_id"] = "different"
    with pytest.raises(ValidationError):
        DryRunTrialRecord.model_validate(payload)

    hiaa = next(item for item in dry_run_fixture.records if item.hiaa_cell is not None)
    payload = hiaa.model_dump(mode="python")
    payload["harm_selector"] = None
    with pytest.raises(ValidationError):
        DryRunTrialRecord.model_validate(payload)

    m2 = next(item for item in dry_run_fixture.records if item.session_observations)
    payload = m2.model_dump(mode="python")
    payload["session_observations"] = (*m2.session_observations, m2.session_observations[0])
    with pytest.raises(ValidationError):
        DryRunTrialRecord.model_validate(payload)


def test_design_and_failure_guards_reject_bad_inputs(
    dry_run_fixture: DryRunFixture,
    tmp_path: Path,
) -> None:
    # Given / When / Then: 非完整 Matrix 与截断结果不能伪装成 720 链报告。
    smoke = load_matrix(T16_DIR / "matrix_smoke.yaml")
    with pytest.raises(DryRunDesignError) as wrong_matrix:
        execute_fake_matrix(dry_run_fixture.registration, smoke, dry_run_fixture.config)
    assert "model1" in str(wrong_matrix.value)
    with pytest.raises(DryRunDesignError):
        build_matrix_integrity_report(
            dry_run_fixture.registration,
            dry_run_fixture.records[:-1],
        )

    # Given / When / Then: 非预算类型、未阻断网络和不足三条的保存演练均失败。
    with pytest.raises(FailureRehearsalError):
        verify_budget_limit(FailureInjectionKind.REFUSAL)

    class UnblockedProbe:
        def attempt(self) -> None:
            return None

    with pytest.raises(FailureRehearsalError):
        verify_network_probe_is_blocked(UnblockedProbe())
    with pytest.raises(FailureRehearsalError) as too_few:
        build_cost_simulation_report(
            dry_run_fixture.config,
            dry_run_fixture.records[:2],
            tmp_path / "never-created.jsonl",
        )
    assert "三条" in str(too_few.value)


def test_refusal_and_no_call_overlap_is_rejected(
    dry_run_fixture: DryRunFixture,
) -> None:
    # Given: 一条可改造成 invalid 分类对照的安全结果。
    safe = next(
        item.result
        for item in dry_run_fixture.records
        if item.result.outcome is TrialOutcome.COMPLETED_WITHOUT_HARM
    )
    payload = safe.model_dump(mode="python")
    payload.update(
        {
            "task_success": False,
            "refusal": True,
            "no_call": True,
            "outcome": TrialOutcome.INVALID,
        }
    )
    overlapping = TrialResult.model_validate(payload)

    # When / Then: 不能把两个信号压成一个操作分类。
    with pytest.raises(FailureRehearsalError):
        operational_disposition(overlapping)
