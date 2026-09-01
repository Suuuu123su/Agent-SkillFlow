from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import JsonValue, ValidationError
from tests.unit.experiment.t16.test_live_agent import _config, _design
from tests.unit.experiment.t16.test_live_records import _record

from skillflow.experiment.t16.live_record_builders import (
    LiveRecordEvidence,
    LiveTaskSuccessBinding,
    build_live_trial_record,
)
from skillflow.experiment.t16.live_records import LiveTrialRecord
from skillflow.experiment.t16.live_store import LiveResultStore
from skillflow.experiment.t16.task_success_evaluator import TaskSuccessEvaluation
from skillflow.experiment.t16.task_success_evidence import (
    AssertionStatus,
    TaskSuccessAggregation,
    TaskSuccessEvidence,
    TaskSuccessResult,
)
from skillflow.schemas import schema_documents


def _v3_payload() -> dict[str, JsonValue]:
    payload = _record().model_dump(mode="json")
    trial_id = payload["result"]["trial_id"]
    evidence = TaskSuccessEvidence(
        evidence_id="evidence-v3",
        run_id="run-v3",
        trial_id=trial_id,
        session_id="session-0",
        assertion_id="output-exists",
        assertion_type="artifact_exists",
        assertion_status=AssertionStatus.PASSED,
        artifact_id="artifact-v3",
        artifact_alias="artifact:task-result",
        artifact_content_sha256="1" * 64,
        effect_id=None,
        receipt_id=None,
        safe_sink_commitment_sha256=None,
        expected_value_commitment_sha256=None,
        observed_value_commitment_sha256=None,
        evaluator_id="skillflow-task-success-evaluator",
        evaluator_version="1.0.0",
        evidence_source="platform_artifact_registry",
        reason_code="assertion_passed",
        created_at=datetime(2026, 8, 29, tzinfo=UTC),
    )
    result = TaskSuccessResult.from_evidence(
        TaskSuccessAggregation(
            trial_id=trial_id,
            evidence=(evidence,),
            evaluator_version="1.0.0",
        )
    )
    payload.update(
        {
            "schema_version": "0.3",
            "run_id": "run-v3",
            "task_success_evidence": [evidence.model_dump(mode="json")],
            "task_success_result": result.model_dump(mode="json"),
        }
    )
    return payload


def test_v03_live_record_binds_structured_task_success_evidence() -> None:
    record = LiveTrialRecord.model_validate(_v3_payload())

    assert record.schema_version == "0.3"
    assert record.result.task_success is True
    assert record.task_success_result is not None
    assert record.task_success_result.evidence_ids == ("evidence-v3",)


def test_v03_rejects_result_evidence_or_run_drift() -> None:
    payload = _v3_payload()
    payload["task_success_evidence"][0]["run_id"] = "other-run"

    with pytest.raises(ValidationError, match="Run"):
        LiveTrialRecord.model_validate(payload)


def test_v03_rejects_evidence_status_partition_drift() -> None:
    payload = _v3_payload()
    payload["task_success_result"].update(
        {
            "passed_assertion_ids": [],
            "failed_assertion_ids": ["output-exists"],
            "task_success": False,
            "status": "failed",
        }
    )
    payload["result"]["task_success"] = False

    with pytest.raises(ValidationError, match=r"Evidence.*聚合"):
        LiveTrialRecord.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [("evaluator_id", "untrusted-evaluator"), ("evaluator_version", "9.9.9")],
)
def test_v03_rejects_unregistered_evaluator(field: str, value: str) -> None:
    payload = _v3_payload()
    payload["task_success_evidence"][0][field] = value
    if field == "evaluator_version":
        payload["task_success_result"][field] = value

    with pytest.raises(ValidationError, match="evaluator"):
        LiveTrialRecord.model_validate(payload)


def test_v02_rejects_backfilled_task_success_evidence() -> None:
    payload = _v3_payload()
    payload["schema_version"] = "0.2"

    with pytest.raises(ValidationError, match="旧记录"):
        LiveTrialRecord.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    ["run_id", "task_success_evidence", "task_success_result"],
)
def test_each_legacy_backfill_field_is_independently_rejected(field: str) -> None:
    v3 = _v3_payload()
    payload = _record().model_dump(mode="json")
    payload[field] = v3[field]

    with pytest.raises(ValidationError, match="旧记录"):
        LiveTrialRecord.model_validate(payload)


def test_v03_preserves_na_without_coercion() -> None:
    payload = _v3_payload()
    payload["task_success_evidence"][0].update(
        {
            "assertion_status": "not_evaluable",
            "artifact_id": None,
            "artifact_content_sha256": None,
            "reason_code": "artifact_registry_unavailable",
        }
    )
    payload["task_success_result"].update(
        {
            "passed_assertion_ids": [],
            "not_evaluable_assertion_ids": ["output-exists"],
            "task_success": None,
            "status": "not_evaluable",
        }
    )
    payload["result"]["task_success"] = None

    record = LiveTrialRecord.model_validate(payload)

    assert record.result.task_success is None


def test_builder_emits_v03_only_when_future_platform_evaluation_is_supplied() -> None:
    base = _record()
    payload = _v3_payload()
    evidence = TaskSuccessEvidence.model_validate(payload["task_success_evidence"][0])
    result = TaskSuccessResult.model_validate(payload["task_success_result"])

    record = build_live_trial_record(
        _design("c1-p11"),
        _config(),
        base.sessions,
        LiveRecordEvidence(
            retry_events=base.retry_events,
            model_revision=base.result.model_revision,
            phase_contract_sha256=base.phase_contract_sha256 or "0" * 64,
        ),
        task_success_binding=LiveTaskSuccessBinding(
            run_id="run-v3",
            evaluation=TaskSuccessEvaluation((evidence,), result),
        ),
    )

    assert record.schema_version == "0.3"
    assert record.run_id == "run-v3"
    assert record.task_success_result == result


def test_v03_store_round_trip_preserves_task_success_evidence(tmp_path: Path) -> None:
    record = LiveTrialRecord.model_validate(_v3_payload())
    store = LiveResultStore(tmp_path / "v03-results.jsonl")
    store.open(resume=False)
    store.append(record)

    resumed = LiveResultStore(store.path)
    resumed.open(resume=True)

    assert resumed.read_records() == (record,)


def test_static_json_schema_enforces_v03_binding_and_legacy_boundary() -> None:
    schema = next(
        item.content
        for item in schema_documents()
        if item.filename == "t16c-live-trial-record.schema.json"
    )
    validator = Draft202012Validator(schema)
    missing_binding = _v3_payload()
    missing_binding["run_id"] = None
    legacy_backfill = _record().model_dump(mode="json")
    legacy_backfill["run_id"] = "forged-run"

    with pytest.raises(JsonSchemaValidationError):
        validator.validate(missing_binding)
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(legacy_backfill)
