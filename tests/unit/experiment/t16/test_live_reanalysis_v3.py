import hashlib
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from tests.unit.experiment.t16.test_live_agent import (
    ScriptedClient,
    _config,
    _design,
    _final_turn,
    _function_turn,
)

from skillflow.experiment.t16 import live_reanalysis_v3 as reanalysis_v3
from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.dry_run_records import SessionEffectObservation
from skillflow.experiment.t16.live_agent import execute_live_trial
from skillflow.experiment.t16.live_reanalysis_v3 import (
    LiveReanalysisPaths,
    LiveReanalysisV3Error,
    LiveReanalysisV3WriteError,
    LoadedLiveReanalysisDesign,
    build_live_reanalysis_v3,
    load_live_reanalysis_design,
    main,
    reanalyze_live_results_v3,
)
from skillflow.experiment.t16.live_reanalysis_v3_metrics import build_audit_metric_bundle
from skillflow.experiment.t16.live_reanalysis_v3_models import (
    AuditEvidenceBasis,
    LiveDesignBinding,
    LiveReanalysisReportV3,
)
from skillflow.experiment.t16.live_records import (
    LiveSessionRecord,
    LiveToolCallAudit,
    LiveTrialRecord,
)
from skillflow.experiment.t16.matrix import MatrixKind, load_matrix
from skillflow.experiment.t16.preregistration import load_preregistration
from skillflow.experiment.t16.preregistration_models import IndependentFactor, PairRole
from skillflow.experiment.t16.trial import TrialOutcome

ROOT = Path(__file__).parents[4]
T16_DIR = ROOT / "experiments" / "t16"
SOURCE_HASH = hashlib.sha256(b"source").hexdigest()


def _record(condition_id: str, *, execute_alias: str | None = None) -> LiveTrialRecord:
    config = _config()
    script = (
        [_function_turn("operation-1"), _final_turn()]
        if execute_alias is not None
        else [_final_turn()]
    )
    return execute_live_trial(
        _design(condition_id),
        config,
        ScriptedClient(script),
        BudgetLedger(config.budget).begin_run(),
    ).record


def _hiaa_records() -> tuple[LiveTrialRecord, ...]:
    return (
        _record("c1-p00"),
        _record("c1-p01"),
        _record("c1-p10"),
        _record("c1-p11"),
    )


def _replace_result_execution(
    record: LiveTrialRecord,
    *,
    executed: bool,
    receipt_id: str | None,
) -> LiveTrialRecord:
    result = record.result.model_copy(
        update={
            "target_effect_requested": executed,
            "target_effect_executed": executed,
            "receipt_id": receipt_id,
            "outcome": TrialOutcome.HARM if executed else TrialOutcome.COMPLETED_WITHOUT_HARM,
        }
    )
    return record.model_copy(
        update={
            "result": result,
            "unauthorized_effect_execution": executed and not record.structured_target_authorized,
        }
    )


def _replace_session(record: LiveTrialRecord, session: LiveSessionRecord) -> LiveTrialRecord:
    return record.model_copy(update={"sessions": (session,)})


def _as_synthetic_m2(record: LiveTrialRecord, session: LiveSessionRecord) -> LiveTrialRecord:
    trial_id = f"live--synthetic-m2-{session.session_index}"
    result = record.result.model_copy(
        update={
            "trial_id": trial_id,
            "condition_id": "m2-target",
            "target_effect_requested": False,
            "target_effect_executed": False,
            "receipt_id": None,
        }
    )
    return _replace_session(record, session).model_copy(
        update={
            "matrix_trial_id": trial_id.removeprefix("live--"),
            "pair_role": PairRole.TARGET,
            "independent_factor": IndependentFactor.MEMORY_SEMANTICS,
            "hiaa_cell": None,
            "harm_selector": None,
            "expected_target_effect_aliases": (),
            "result": result,
        }
    )


def _with_identity(record: LiveTrialRecord, trial_id: str) -> LiveTrialRecord:
    return record.model_copy(
        update={
            "matrix_trial_id": trial_id.removeprefix("live--"),
            "result": record.result.model_copy(update={"trial_id": trial_id}),
        }
    )


def _subset_design(records: tuple[LiveTrialRecord, ...]) -> LoadedLiveReanalysisDesign:
    loaded = load_live_reanalysis_design(
        T16_DIR / "preregistration_t16c_v2.yaml",
        T16_DIR / "matrix_model1_t16c_v2.yaml",
    )
    matrix_ids = {item.matrix_trial_id for item in records}
    matrix = loaded.matrix.model_copy(
        update={
            "trials": tuple(item for item in loaded.matrix.trials if item.trial_id in matrix_ids)
        }
    )
    return LoadedLiveReanalysisDesign(
        preregistration_path=loaded.preregistration_path,
        matrix_path=loaded.matrix_path,
        preregistration_sha256=loaded.preregistration_sha256,
        matrix_sha256=loaded.matrix_sha256,
        registration=loaded.registration,
        matrix=matrix,
        expected_trial_ids=tuple(sorted(item.result.trial_id for item in records)),
    )


def _binding() -> LiveDesignBinding:
    return LiveDesignBinding(
        preregistration_path="preregistration.yaml",
        preregistration_sha256=SOURCE_HASH,
        preregistration_id="prereg",
        preregistration_schema_version="0.2",
        matrix_path="matrix.yaml",
        matrix_sha256=SOURCE_HASH,
        matrix_id="matrix",
        matrix_schema_version="0.2",
        expected_trial_count=2,
        expected_trial_ids=("live--a", "live--b"),
        observed_trial_ids=("live--a", "live--b"),
        model_input_manifest_sha256=SOURCE_HASH,
        unique_model_input_count=2,
    )


def _report() -> LiveReanalysisReportV3:
    records = _hiaa_records()
    return build_live_reanalysis_v3(
        records,
        "trial-results.jsonl",
        SOURCE_HASH,
        _subset_design(records),
    )


def test_v3_hiaa_uses_matching_accepted_audit_not_trial_result() -> None:
    records = list(_hiaa_records())
    records[-1] = _replace_result_execution(records[-1], executed=True, receipt_id="forged")

    forged = build_audit_metric_bundle(tuple(records))

    assert forged.hiaa.p11.execution.executed_count == 0

    actual = _record("c1-p11", execute_alias="context-harm")
    actual = _replace_result_execution(actual, executed=False, receipt_id=None)
    records[-1] = actual

    audited = build_audit_metric_bundle(tuple(records))

    assert audited.hiaa.p11.execution.executed_count == 1
    assert audited.hiaa.p11.execution.receipt_ids


def test_v3_authorization_execution_uses_audit_even_when_trial_result_is_false() -> None:
    record = _record("a1-claim", execute_alias="authorization-send")
    assert record.expected_target_effect_aliases == ("authorization-send",)
    record = _replace_result_execution(record, executed=False, receipt_id=None)

    bundle = build_audit_metric_bundle((*_hiaa_records(), record))
    claim = next(
        item for item in bundle.authorization_operational_rates if item.condition_id == "a1-claim"
    )

    assert claim.execution.executed_count == 1
    assert bundle.target_execution_authorization.structured_unauthorized_execution_count == 1


def test_v3_refusal_is_not_counted_as_valid_zero() -> None:
    records = list(_hiaa_records())
    refusal = records[0]
    result = refusal.result.model_copy(
        update={
            "task_success": False,
            "refusal": True,
            "outcome": TrialOutcome.INVALID,
        }
    )
    records[0] = refusal.model_copy(update={"result": result})

    bundle = build_audit_metric_bundle(tuple(records))

    accounting = bundle.hiaa.p00.execution.observations
    assert accounting.observed_count == 1
    assert accounting.valid_count == 0
    assert accounting.refusal_count == 1
    assert bundle.hiaa.p00.execution.valid_rate.value is None


def test_v3_m2_rejects_cross_session_alias_and_marks_primary_audit_basis() -> None:
    base = _record("c1-p00")
    session = base.sessions[0].model_copy(
        update={
            "session_index": 1,
            "expected_target_effect_aliases": ("residual-send-1",),
            "tool_calls": (
                LiveToolCallAudit(
                    session_index=1,
                    call_id="call-cross-session",
                    tool_name="skillflow_safe_effect",
                    accepted=True,
                    effect_alias="residual-send-3",
                    receipt_id="receipt-cross-session",
                ),
            ),
        }
    )
    record = _as_synthetic_m2(base, session)

    bundle = build_audit_metric_bundle((*_hiaa_records(), record))
    session_1 = next(
        item
        for item in bundle.m2_operational_rates
        if item.pair_role is PairRole.TARGET and item.session_index == 1
    )

    assert session_1.execution.executed_count == 0
    assert bundle.evidence_basis.m2_execution_basis == "per_session_expected_alias_tool_audit"
    assert bundle.evidence_basis.legacy_m2_fallback_trial_ids == ()


def test_v3_m2_legacy_fallback_is_explicitly_limited() -> None:
    base = _record("c1-p00")
    session = base.sessions[0].model_copy(
        update={"session_index": 1, "expected_target_effect_aliases": ()}
    )
    record = _as_synthetic_m2(base, session).model_copy(
        update={
            "session_observations": (
                SessionEffectObservation(
                    session_index=1,
                    target_effect_requested=True,
                    target_effect_executed=True,
                    receipt_id="legacy-receipt",
                ),
            )
        }
    )

    bundle = build_audit_metric_bundle((*_hiaa_records(), record))
    session_1 = next(
        item
        for item in bundle.m2_operational_rates
        if item.pair_role is PairRole.TARGET and item.session_index == 1
    )

    assert session_1.execution.executed_count == 1
    assert bundle.evidence_basis.m2_execution_basis == "legacy_session_observation_fallback"
    assert bundle.evidence_basis.legacy_m2_fallback_trial_ids == (record.result.trial_id,)
    assert bundle.evidence_basis.compatibility_limitations


def test_v3_reanalysis_rejects_partial_jsonl_against_bound_matrix(tmp_path: Path) -> None:
    source = tmp_path / "trial-results.jsonl"
    source.write_text(f"{_record('c1-p00').model_dump_json()}\n", encoding="utf-8")
    output = tmp_path / "metrics-reanalysis-v0.3.json"
    paths = LiveReanalysisPaths(
        source_path=source,
        output_path=output,
        preregistration_path=T16_DIR / "preregistration_t16c_v2.yaml",
        matrix_path=T16_DIR / "matrix_model1_t16c_v2.yaml",
    )

    with pytest.raises(LiveReanalysisV3Error, match="完整集合"):
        reanalyze_live_results_v3(paths)

    assert not output.exists()


def test_v3_design_binding_uses_v2_and_expected_live_trial_ids() -> None:
    design = load_live_reanalysis_design(
        T16_DIR / "preregistration_t16c_v2.yaml",
        T16_DIR / "matrix_model1_t16c_v2.yaml",
    )

    assert design.registration.schema_version == "0.2"
    assert design.matrix.schema_version == "0.2"
    assert len(design.expected_trial_ids) == 360
    assert design.expected_trial_ids[0].startswith("live--model1-")
    assert len(set(design.expected_trial_ids)) == 360


def test_v3_design_binding_accepts_original_v1_for_historical_evidence() -> None:
    design = load_live_reanalysis_design(
        T16_DIR / "preregistration.yaml",
        T16_DIR / "matrix_model1.yaml",
    )

    assert design.registration.schema_version == "0.1"
    assert design.matrix.schema_version == "0.1"
    assert len(design.expected_trial_ids) == 360
    assert len(set(design.expected_trial_ids)) == 360


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {
                "expected_trial_ids": ("live--b", "live--a"),
                "observed_trial_ids": ("live--b", "live--a"),
            },
            "确定排序",
        ),
        (
            {
                "expected_trial_ids": ("live--a", "live--a"),
                "observed_trial_ids": ("live--a", "live--a"),
            },
            "不能重复",
        ),
        ({"expected_trial_count": 1}, "expected_trial_count"),
        ({"matrix_schema_version": "0.1"}, "Schema 版本"),
        ({"observed_trial_ids": ("live--a", "live--c")}, "完整集合"),
        ({"unique_model_input_count": 3}, "唯一模型输入数"),
    ],
)
def test_v3_design_binding_rejects_inconsistent_public_contract(
    updates: dict[str, Any],
    message: str,
) -> None:
    payload = _binding().model_dump(mode="json")
    payload.update(updates)

    with pytest.raises(ValidationError, match=message):
        LiveDesignBinding.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "m2_execution_basis": "legacy_session_observation_fallback",
            "legacy_m2_fallback_trial_ids": ("live--a", "live--a"),
            "compatibility_limitations": ("legacy",),
        },
        {
            "m2_execution_basis": "per_session_expected_alias_tool_audit",
            "legacy_m2_fallback_trial_ids": ("live--a",),
            "compatibility_limitations": ("legacy",),
        },
        {
            "m2_execution_basis": "per_session_expected_alias_tool_audit",
            "authorization_alias_unavailable_trial_ids": ("live--a",),
        },
    ],
)
def test_v3_evidence_basis_rejects_hidden_or_inconsistent_fallback(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        AuditEvidenceBasis.model_validate(payload)


@pytest.mark.parametrize("case", ["legacy", "provenance", "binding"])
def test_v3_report_rejects_open_source_accounting(case: str) -> None:
    payload = _report().model_dump(mode="json")
    if case == "legacy":
        payload["source_record_count"] = 5
    elif case == "provenance":
        payload["provenance_not_available_count"] = 3
    else:
        payload["source_record_count"] = 5
        payload["provenance_not_available_count"] = 5
        legacy = payload["legacy_outcomes"]
        assert isinstance(legacy, dict)
        legacy["completed_without_harm_count"] = 5

    with pytest.raises(ValidationError):
        LiveReanalysisReportV3.model_validate(payload)


def test_v3_build_report_binds_input_manifest_and_legacy_outcomes() -> None:
    records = _hiaa_records()

    report = build_live_reanalysis_v3(
        tuple(reversed(records)),
        "trial-results.jsonl",
        SOURCE_HASH,
        _subset_design(records),
    )

    expected_manifest = "".join(
        f"{item.result.trial_id}\t{item.model_input_sha256}\n"
        for item in sorted(records, key=lambda record: record.result.trial_id)
    )
    assert (
        report.design_binding.model_input_manifest_sha256
        == hashlib.sha256(expected_manifest.encode()).hexdigest()
    )
    assert report.legacy_outcomes.completed_without_harm_count == 4
    assert report.formal_uea.metric.denominator == 0


def test_v3_build_rejects_duplicate_matrix_and_result_id_mismatches() -> None:
    records = _hiaa_records()
    design = _subset_design(records)

    with pytest.raises(LiveReanalysisV3Error, match="重复 trial_id"):
        build_live_reanalysis_v3((records[0], records[0]), "source", SOURCE_HASH, design)

    bad_matrix_record = records[0].model_copy(update={"matrix_trial_id": "wrong-matrix-id"})
    with pytest.raises(LiveReanalysisV3Error, match="matrix_trial_id"):
        build_live_reanalysis_v3(
            (bad_matrix_record, *records[1:]),
            "source",
            SOURCE_HASH,
            design,
        )

    forged = records[0].model_copy(
        update={"result": records[0].result.model_copy(update={"trial_id": "live--forged"})}
    )
    forged_records = tuple(sorted((forged, *records[1:]), key=lambda item: item.result.trial_id))
    forged_design = design.__class__(
        preregistration_path=design.preregistration_path,
        matrix_path=design.matrix_path,
        preregistration_sha256=design.preregistration_sha256,
        matrix_sha256=design.matrix_sha256,
        registration=design.registration,
        matrix=design.matrix,
        expected_trial_ids=tuple(item.result.trial_id for item in forged_records),
    )
    with pytest.raises(LiveReanalysisV3Error, match="稳定映射"):
        build_live_reanalysis_v3(forged_records, "source", SOURCE_HASH, forged_design)


def test_v3_design_loader_rejects_drift_version_and_matrix_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registration = load_preregistration(T16_DIR / "preregistration_t16c_v2.yaml")
    matrix = load_matrix(T16_DIR / "matrix_model1_t16c_v2.yaml")
    monkeypatch.setattr(reanalysis_v3, "load_preregistration", lambda _path: registration)

    hashes = iter(("0" * 64, "1" * 64, "2" * 64, "1" * 64))
    monkeypatch.setattr(reanalysis_v3, "_sha256", lambda _path: next(hashes))
    monkeypatch.setattr(reanalysis_v3, "load_matrix", lambda _path: matrix)
    with pytest.raises(LiveReanalysisV3Error, match="读取期间冻结设计"):
        load_live_reanalysis_design(Path("prereg"), Path("matrix"))

    monkeypatch.setattr(reanalysis_v3, "_sha256", lambda _path: "0" * 64)
    mismatched = matrix.model_copy(update={"schema_version": "0.1"})
    monkeypatch.setattr(reanalysis_v3, "load_matrix", lambda _path: mismatched)
    with pytest.raises(LiveReanalysisV3Error, match="相同"):
        load_live_reanalysis_design(Path("prereg"), Path("matrix"))

    smoke = matrix.model_copy(update={"kind": MatrixKind.SMOKE})
    monkeypatch.setattr(reanalysis_v3, "load_matrix", lambda _path: smoke)
    with pytest.raises(LiveReanalysisV3Error, match="model1"):
        load_live_reanalysis_design(Path("prereg"), Path("matrix"))


def test_v3_reanalysis_detects_source_drift_before_design_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EmptyStore:
        def __init__(self, _path: Path) -> None:
            pass

        def read_records(self) -> tuple[LiveTrialRecord, ...]:
            return ()

    hashes = iter(("0" * 64, "1" * 64))
    monkeypatch.setattr(reanalysis_v3, "_sha256", lambda _path: next(hashes))
    monkeypatch.setattr(reanalysis_v3, "LiveResultStore", EmptyStore)
    paths = LiveReanalysisPaths(Path("source"), Path("output"), Path("prereg"), Path("matrix"))

    with pytest.raises(LiveReanalysisV3Error, match=r"trial-results\.jsonl 发生变化"):
        reanalyze_live_results_v3(paths)


def test_v3_reanalysis_writes_exclusively_and_formats_write_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = _hiaa_records()
    source = tmp_path / "trial-results.jsonl"
    source.write_text("".join(f"{item.model_dump_json()}\n" for item in records), encoding="utf-8")
    output = tmp_path / "metrics-reanalysis-v0.3.json"
    design = _subset_design(records)
    monkeypatch.setattr(reanalysis_v3, "load_live_reanalysis_design", lambda *_args: design)
    paths = LiveReanalysisPaths(source, output, Path("prereg"), Path("matrix"))

    report = reanalyze_live_results_v3(paths)

    assert report.source_record_count == 4
    assert output.is_file()
    with pytest.raises(LiveReanalysisV3WriteError) as captured:
        reanalyze_live_results_v3(paths)
    assert "metrics-reanalysis-v0.3.json" in str(captured.value)


def test_v3_cli_maps_all_required_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[LiveReanalysisPaths] = []
    monkeypatch.setattr(reanalysis_v3, "reanalyze_live_results_v3", captured.append)

    exit_code = main(
        [
            "--source",
            "source.jsonl",
            "--output",
            "report.json",
            "--preregistration",
            "prereg.yaml",
            "--matrix",
            "matrix.yaml",
        ]
    )

    assert exit_code == 0
    assert captured == [
        LiveReanalysisPaths(
            Path("source.jsonl"),
            Path("report.json"),
            Path("prereg.yaml"),
            Path("matrix.yaml"),
        )
    ]


def test_v3_missing_source_is_reported_as_reanalysis_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"

    with pytest.raises(LiveReanalysisV3Error, match=r"missing\.jsonl"):
        reanalyze_live_results_v3(
            LiveReanalysisPaths(missing, tmp_path / "out.json", Path("p"), Path("m"))
        )


def test_v3_metric_rejects_invalid_hiaa_and_duplicate_trials_but_dedupes_receipts() -> None:
    records = list(_hiaa_records())
    records[0] = records[0].model_copy(update={"harm_selector": None})
    with pytest.raises(ValueError, match="HIAA 四格"):
        build_audit_metric_bundle(tuple(records))

    duplicate = _record("c1-p00")
    with pytest.raises(ValueError, match="重复 trial_id"):
        build_audit_metric_bundle((duplicate, duplicate))

    authorization = _record("a1-claim", execute_alias="authorization-send")
    first = authorization.sessions[0].tool_calls[0]
    second = first.model_copy(update={"call_id": "call-second", "receipt_id": "receipt-second"})
    session = authorization.sessions[0].model_copy(update={"tool_calls": (first, second)})
    authorization = authorization.model_copy(update={"sessions": (session,)})
    bundle = build_audit_metric_bundle((*_hiaa_records(), authorization))
    claim = next(
        item for item in bundle.authorization_operational_rates if item.condition_id == "a1-claim"
    )

    assert claim.execution.executed_count == 1
    assert claim.execution.receipt_ids == (first.receipt_id,)


def test_v3_metric_exposes_missing_authorization_and_target_aliases() -> None:
    authorization = _record("a1-claim")
    auth_session = authorization.sessions[0].model_copy(
        update={"expected_target_effect_aliases": ()}
    )
    authorization = authorization.model_copy(
        update={"expected_target_effect_aliases": (), "sessions": (auth_session,)}
    )

    unbound = _record("c1-p11", execute_alias="context-harm")
    unbound_session = unbound.sessions[0].model_copy(update={"expected_target_effect_aliases": ()})
    unbound = _with_identity(unbound, "live--unbound-receipt").model_copy(
        update={
            "result": _with_identity(unbound, "live--unbound-receipt").result.model_copy(
                update={"condition_id": "b0"}
            ),
            "hiaa_cell": None,
            "harm_selector": None,
            "expected_target_effect_aliases": (),
            "sessions": (unbound_session,),
        }
    )

    bundle = build_audit_metric_bundle((*_hiaa_records(), authorization, unbound))
    claim = next(
        item for item in bundle.authorization_operational_rates if item.condition_id == "a1-claim"
    )

    assert claim.execution.observations.valid_count == 0
    assert bundle.evidence_basis.authorization_alias_unavailable_trial_ids == (
        authorization.result.trial_id,
    )
    assert bundle.evidence_basis.target_alias_unavailable_trial_ids == (unbound.result.trial_id,)
    assert len(bundle.evidence_basis.compatibility_limitations) == 2


def test_v3_metric_handles_legacy_false_missing_observation_and_mixed_basis() -> None:
    base = _record("c1-p00")
    legacy_session = base.sessions[0].model_copy(
        update={"session_index": 3, "expected_target_effect_aliases": ()}
    )
    missing = _as_synthetic_m2(base, legacy_session)
    with pytest.raises(ValueError, match="缺少唯一 observation"):
        build_audit_metric_bundle((*_hiaa_records(), missing))

    legacy = missing.model_copy(
        update={
            "session_observations": (
                SessionEffectObservation(
                    session_index=3,
                    target_effect_requested=False,
                    target_effect_executed=False,
                    receipt_id=None,
                ),
            )
        }
    )
    primary_session = base.sessions[0].model_copy(
        update={"session_index": 1, "expected_target_effect_aliases": ("residual-send-1",)}
    )
    primary = _as_synthetic_m2(base, primary_session)

    bundle = build_audit_metric_bundle((*_hiaa_records(), primary, legacy))

    assert bundle.evidence_basis.m2_execution_basis == (
        "mixed_per_session_audit_and_legacy_observation"
    )
    assert legacy.result.trial_id in bundle.evidence_basis.legacy_m2_fallback_trial_ids


def test_v3_metric_uses_harm_selector_fallback_and_rejects_duplicate_session() -> None:
    executed = _record("c1-p11", execute_alias="context-harm")
    executed = executed.model_copy(update={"expected_target_effect_aliases": ()})
    records = list(_hiaa_records())
    records[-1] = executed

    bundle = build_audit_metric_bundle(tuple(records))

    assert executed.result.trial_id in bundle.target_execution_authorization.target_trial_ids

    base = _record("c1-p00")
    session = base.sessions[0].model_copy(
        update={"session_index": 1, "expected_target_effect_aliases": ("residual-send-1",)}
    )
    duplicated = _as_synthetic_m2(base, session).model_copy(update={"sessions": (session, session)})
    with pytest.raises(ValueError, match="Session 1 重复"):
        build_audit_metric_bundle((*_hiaa_records(), duplicated))
