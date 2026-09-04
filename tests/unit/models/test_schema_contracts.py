import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import JsonValue, ValidationError

from skillflow.experiment.t17.v2.schema_models import v2_schema_documents
from skillflow.models import ExperimentMatrix, SkillManifest
from skillflow.models.reports import RISK_REPORT_ADAPTER
from skillflow.schemas import schema_documents

SCHEMA_DIR = Path("schemas")


def valid_manifest_payload() -> dict[str, JsonValue]:
    return {
        "schema_version": "0.1",
        "id": "safe-reader",
        "principal_type": "skill",
        "description": "只读取一个精确文件",
        "requested_permissions": [
            {
                "source": "workspace:/report.txt",
                "action": "file.read",
                "sink": "context:/task",
                "scope": "exact-file",
                "lifetime": "call",
                "sensitivity": 1,
            }
        ],
    }


def valid_matrix_payload() -> dict[str, JsonValue]:
    return {
        "schema_version": "0.1",
        "id": "mvp",
        "variants": [
            {
                "variant": "baseline",
                "scenario": "scenarios/b0.yaml",
                "seed": 7,
                "target_skill_present": True,
                "shared_context": False,
                "persistent_memory": False,
                "auto_approve_tools": False,
                "enforcement_mode": "enforce",
                "provenance_mode": "preserve",
                "implicit_text_authorization": False,
            }
        ],
    }


def valid_risk_report_payload() -> dict[str, JsonValue]:
    not_applicable: dict[str, JsonValue] = {
        "numerator": 0,
        "denominator": 0,
        "value": None,
        "status": "not_applicable",
        "evidence_ids": [],
    }
    return {
        "schema_version": "0.1",
        "report_scope": "run",
        "run_id": "run-1",
        "scenario_id": "scenario-1",
        "uea": {
            "uea_count": 0,
            "uea_type_count": 0,
            "uea_weight": 0.0,
            "evidence_ids": [],
            "canonical_effect_keys": [],
        },
        "provenance": {
            "overall": {
                "counts": {"tp": 0, "fp": 0, "fn": 0, "artifact_ids": []},
                "precision": not_applicable,
                "recall": not_applicable,
                "f1": not_applicable,
            },
            "by_boundary_depth": [],
        },
        "unauthorized_effects": [],
    }


def test_experiment_matrix_round_trip_and_duplicate_rejection() -> None:
    matrix = ExperimentMatrix.model_validate(valid_matrix_payload())
    assert ExperimentMatrix.model_validate_json(matrix.model_dump_json()) == matrix

    payload = valid_matrix_payload()
    variants = payload["variants"]
    assert isinstance(variants, list)
    variant = variants[0]
    assert isinstance(variant, dict)
    variants.append(dict(variant))
    with pytest.raises(ValidationError, match="重复"):
        ExperimentMatrix.model_validate(payload)


def test_risk_report_discriminator_is_closed() -> None:
    report = RISK_REPORT_ADAPTER.validate_python(valid_risk_report_payload())
    assert RISK_REPORT_ADAPTER.validate_json(RISK_REPORT_ADAPTER.dump_json(report)) == report

    payload = valid_risk_report_payload()
    payload["report_scope"] = "unknown"
    with pytest.raises(ValidationError):
        RISK_REPORT_ADAPTER.validate_python(payload)


def test_static_schemas_equal_model_generated_schemas() -> None:
    documents = schema_documents()
    assert {document.filename for document in documents} == {
        "skill-manifest.schema.json",
        "scenario.schema.json",
        "experiment-matrix.schema.json",
        "risk-report.schema.json",
        "t16-trial-result.schema.json",
        "t16-budget.schema.json",
        "t16-provider.schema.json",
        "t16b-dry-run-summary.schema.json",
        "t16c-live-config.schema.json",
        "t16e-live-config.schema.json",
        "t16c-live-trial-record.schema.json",
        "t16c-live-phase-summary.schema.json",
        "t16c-live-metrics.schema.json",
        "t16c-live-reanalysis.schema.json",
        "t16c-live-reanalysis-v0.3.schema.json",
        "t16c-live-reanalysis-v0.4.schema.json",
        "t16-task-success-evidence.schema.json",
        "t16-task-success-result.schema.json",
        "t16-task-result-v3.schema.json",
        "t16-task-success-specifications-v3.schema.json",
        "t16-task-success-preregistration-v3.schema.json",
        "t16-task-success-smoke-matrix-v3.schema.json",
        "t16c-v2-partial-reanalysis-v0.5.schema.json",
        "t16d2-raw-trial-record.schema.json",
        "t16d2-preflight.schema.json",
        "t16d2-stage-gate.schema.json",
        "t16d2-checkpoint.schema.json",
        "t16d2-run-summary.schema.json",
        "t16d2r-usage-event.schema.json",
        "t16d2-v31-canary-usage-event.schema.json",
        "t16d2-v31-canary-run-summary.schema.json",
        "t16d2-bridge-report.schema.json",
        "t16e-cross-model-comparison.schema.json",
        "t17-baseline-audit.schema.json",
        "t17-evidence-domain.schema.json",
        "t17-hook-capability.schema.json",
        "t17-ratio-measurement.schema.json",
        "t17-reference-observations.schema.json",
        "t17-scenario-measurements.schema.json",
        "t17-scripted-golden.schema.json",
        "t17-scripted-summary.schema.json",
        "t17-budget-proposal.schema.json",
        "t17-live-matrix.schema.json",
        "t17-live-preregistration.schema.json",
        "t17-approved-live-config.schema.json",
        "t17-budget-approval.schema.json",
        "t17-live-preflight.schema.json",
        "t17-live-unit-record.schema.json",
        "t17-live-stage-summary.schema.json",
        "t17-live-journal-event.schema.json",
        "t17-interval-estimate.schema.json",
        "t17-phase-metrics.schema.json",
        "t17-cross-model.schema.json",
        "t17-defense-report.schema.json",
        "t17-final-metrics.schema.json",
        "t17-task-success-evidence.schema.json",
        "t17-minimal-configuration.schema.json",
        "t17-minimal-normal-task-contract.schema.json",
        "t17-minimal-normal-task-evidence.schema.json",
        "t17-minimal-phase-contract.schema.json",
        "t17-minimal-run-record.schema.json",
        "t17-minimal-raw-manifest.schema.json",
        "t17-minimal-execution-status.schema.json",
        "t17-minimal-measurement.schema.json",
        "t17-minimal-domain-report.schema.json",
        "t17-minimal-graph.schema.json",
        "t17-minimal-replay-pair.schema.json",
        "t17-minimal-run-risk.schema.json",
        "t17-minimal-replay-risk.schema.json",
        "t17-minimal-observed-trace.schema.json",
        "t17-minimal-oracle-trace.schema.json",
        "t17-minimal-tool-receipt.schema.json",
    } | {name for name, _ in v2_schema_documents()}
    for document in documents:
        static_schema = json.loads((SCHEMA_DIR / document.filename).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(static_schema)
        assert static_schema == document.content


def test_manifest_model_and_json_schema_accept_same_valid_document() -> None:
    payload = valid_manifest_payload()
    manifest = SkillManifest.model_validate(payload)
    manifest_schema = next(
        document.content
        for document in schema_documents()
        if document.filename == "skill-manifest.schema.json"
    )

    Draft202012Validator(manifest_schema).validate(payload)
    assert manifest.id == "safe-reader"


def test_manifest_accepts_declared_permissions_compatibility_name() -> None:
    payload = valid_manifest_payload()
    payload["declared_permissions"] = payload.pop("requested_permissions")

    manifest = SkillManifest.model_validate(payload)
    schema = next(
        document.content
        for document in schema_documents()
        if document.filename == "skill-manifest.schema.json"
    )

    Draft202012Validator(schema).validate(payload)
    assert len(manifest.declared_permissions) == 1


def test_manifest_rejects_two_nonempty_permission_fields() -> None:
    payload = valid_manifest_payload()
    payload["declared_permissions"] = payload["requested_permissions"]

    with pytest.raises(ValidationError, match="不能同时非空"):
        SkillManifest.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "unknown_value"),
    [("action", "file.teleport"), ("lifetime", "forever")],
)
def test_manifest_model_and_schema_reject_unknown_closed_value(
    field: str,
    unknown_value: str,
) -> None:
    payload = valid_manifest_payload()
    permissions = payload["requested_permissions"]
    assert isinstance(permissions, list)
    permission = permissions[0]
    assert isinstance(permission, dict)
    permission[field] = unknown_value

    with pytest.raises(ValidationError):
        SkillManifest.model_validate(payload)
    schema = next(
        document.content
        for document in schema_documents()
        if document.filename == "skill-manifest.schema.json"
    )
    with pytest.raises(JsonSchemaValidationError):
        Draft202012Validator(schema).validate(payload)
