import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest
from tests.unit.experiment.t16.test_live_reanalysis_v3 import (
    _hiaa_records,
    _record,
    _subset_design,
)

from skillflow.experiment.t16 import live_reanalysis_v4
from skillflow.experiment.t16.live_reanalysis_v4 import (
    LiveReanalysisPaths,
    LiveReanalysisV4Error,
    LiveReanalysisV4WriteError,
    build_live_reanalysis_v4,
    reanalyze_live_results_v4,
)
from skillflow.experiment.t16.live_reanalysis_v4_models import LiveReanalysisReportV4
from skillflow.experiment.t16.live_records import LiveTrialRecord
from skillflow.experiment.t16.preregistration_models import (
    IndependentFactor,
    PairRole,
    T16Intervention,
)
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.metrics import MetricStatus
from skillflow.models.references import EffectSelectorRef, ScenarioPath

SOURCE_HASH = hashlib.sha256(b"source-v4").hexdigest()
RecordMutation = Callable[[LiveTrialRecord], LiveTrialRecord]


def _build(records: tuple[LiveTrialRecord, ...]) -> LiveReanalysisReportV4:
    return build_live_reanalysis_v4(
        records,
        "trial-results.jsonl",
        SOURCE_HASH,
        _subset_design(records),
    )


def _historical(record: LiveTrialRecord) -> LiveTrialRecord:
    return record.model_copy(update={"schema_version": "0.1", "phase_contract_sha256": None})


def _replace_result_field(
    record: LiveTrialRecord,
    field: str,
    value: str | int | ScenarioPath,
) -> LiveTrialRecord:
    return record.model_copy(update={"result": record.result.model_copy(update={field: value})})


def test_v4_versions_correction_and_phase_contract_binding() -> None:
    records = _hiaa_records()
    report = _build(records)
    assert report.schema_version == "0.4"
    assert report.correction_of == "t16c-live-reanalysis-v0.3"
    assert report.design_binding.phase_contract.status == "available"
    assert report.design_binding.phase_contract.sha256 == records[0].phase_contract_sha256
    assert report.design_binding.compatibility_limitations == ()


def test_v4_historical_v01_phase_contract_is_structured_na() -> None:
    records = tuple(_historical(item) for item in _hiaa_records())
    report = _build(records)
    binding = report.design_binding.phase_contract
    assert binding.status == "not_available"
    assert binding.sha256 is None
    assert binding.reason is not None
    assert binding.unavailable_trial_ids == tuple(sorted(item.result.trial_id for item in records))
    assert report.design_binding.compatibility_limitations

    claimed = tuple(item.model_copy(update={"phase_contract_sha256": "a" * 64}) for item in records)
    assert _build(claimed).design_binding.phase_contract.status == "not_available"


def test_v4_rejects_missing_or_mixed_v02_phase_contract() -> None:
    records = list(_hiaa_records())
    records[0] = records[0].model_copy(update={"phase_contract_sha256": None})
    with pytest.raises(LiveReanalysisV4Error, match=r"0.2.*phase contract"):
        _build(tuple(records))
    records = list(_hiaa_records())
    records[0] = records[0].model_copy(update={"phase_contract_sha256": "f" * 64})
    with pytest.raises(LiveReanalysisV4Error, match=r"phase contract.*一致"):
        _build(tuple(records))


def test_v4_alias_unavailable_rates_are_na_and_lower_bound_lists_receipt() -> None:
    records = tuple(_historical(item) for item in _hiaa_records())
    authorization = _historical(_record("a1-claim", execute_alias="authorization-send"))
    session = authorization.sessions[0].model_copy(update={"expected_target_effect_aliases": ()})
    authorization = authorization.model_copy(
        update={"expected_target_effect_aliases": (), "sessions": (session,)}
    )
    report = _build((*records, authorization))
    claim = next(
        item for item in report.authorization_operational_rates if item.condition_id == "a1-claim"
    )
    first_receipt = session.tool_calls[0].receipt_id
    assert claim.execution.evidence_status == "not_available"
    assert claim.execution.scheduled_rate.status is MetricStatus.NOT_APPLICABLE
    assert claim.execution.observed_rate.status is MetricStatus.NOT_APPLICABLE
    assert report.target_execution_authorization.count_semantics == ("identifiable_lower_bound")
    assert report.target_execution_authorization.unclassified_receipt_ids == (first_receipt,)
    assert report.operational_design_labeled_uea.count_semantics == ("identifiable_lower_bound")
    assert report.operational_design_labeled_uea.unclassified_receipt_ids == (first_receipt,)


def test_v4_multiple_receipts_count_trial_once_and_select_first_raw_receipt() -> None:
    authorization = _record("a1-claim", execute_alias="authorization-send")
    first = authorization.sessions[0].tool_calls[0]
    second = first.model_copy(update={"call_id": "call-second", "receipt_id": "receipt-second"})
    session = authorization.sessions[0].model_copy(update={"tool_calls": (first, second)})
    authorization = authorization.model_copy(update={"sessions": (session,)})
    report = _build((*_hiaa_records(), authorization))
    claim = next(
        item for item in report.authorization_operational_rates if item.condition_id == "a1-claim"
    )
    assert claim.execution.executed_count == 1
    assert claim.execution.receipt_ids == (first.receipt_id,)
    assert report.target_execution_authorization.target_execution_count == 1
    assert report.target_execution_authorization.receipt_ids == (first.receipt_id,)


@pytest.mark.parametrize(
    ("field", "mutation"),
    [
        (
            "scenario",
            lambda item: _replace_result_field(
                item,
                "scenario",
                ScenarioPath("scenarios/benign/n0_irrelevant_text.yaml"),
            ),
        ),
        ("condition_id", lambda item: _replace_result_field(item, "condition_id", "g0")),
        (
            "semantic_instance_id",
            lambda item: _replace_result_field(item, "semantic_instance_id", "wrong-v01"),
        ),
        ("pair_id", lambda item: _replace_result_field(item, "pair_id", "wrong-pair")),
        ("repeat_index", lambda item: _replace_result_field(item, "repeat_index", 99)),
        ("pair_role", lambda item: item.model_copy(update={"pair_role": PairRole.TARGET})),
        (
            "independent_factor",
            lambda item: item.model_copy(
                update={"independent_factor": IndependentFactor.SKILL_SEMANTICS}
            ),
        ),
        ("hiaa_cell", lambda item: item.model_copy(update={"hiaa_cell": HiaaCell.P00})),
        (
            "harm_selector",
            lambda item: item.model_copy(
                update={"harm_selector": EffectSelectorRef("effect-selector:wrong")}
            ),
        ),
        (
            "intervention",
            lambda item: item.model_copy(
                update={"intervention": T16Intervention.NEUTRALIZE_AUTHORIZATION_CLAIM}
            ),
        ),
    ],
)
def test_v4_rejects_record_metadata_drift(
    field: str,
    mutation: RecordMutation,
) -> None:
    base = _record("b0")
    records = (*_hiaa_records(), mutation(base))
    with pytest.raises(LiveReanalysisV4Error, match=field):
        _build(records)


def test_v4_offline_write_is_exclusive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = _hiaa_records()
    source = tmp_path / "trial-results.jsonl"
    source.write_text(
        "".join(f"{item.model_dump_json()}\n" for item in records),
        encoding="utf-8",
    )
    paths = LiveReanalysisPaths(
        source_path=source,
        output_path=tmp_path / "metrics-reanalysis-v0.4.json",
        preregistration_path=Path("prereg.yaml"),
        matrix_path=Path("matrix.yaml"),
    )
    monkeypatch.setattr(
        live_reanalysis_v4,
        "load_live_reanalysis_design",
        lambda *_args: _subset_design(records),
    )
    report = reanalyze_live_results_v4(paths)
    assert report.schema_version == "0.4"
    with pytest.raises(LiveReanalysisV4WriteError):
        reanalyze_live_results_v4(paths)
