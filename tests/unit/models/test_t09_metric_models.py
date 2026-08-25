import pytest
from pydantic import ValidationError

from skillflow.models.metrics import RatioMetric, UnauthorizedEffectEvidence
from skillflow.models.reports import RISK_REPORT_ADAPTER


def test_run_report_accepts_structured_t09_metrics_with_evidence() -> None:
    # Given: 一个含 UEA 实例证据和完整比例分子/分母的 Run 报告
    payload = {
        "schema_version": "0.1",
        "report_scope": "run",
        "run_id": "run-1",
        "scenario_id": "scenario-1",
        "uea": {
            "uea_count": 1,
            "uea_type_count": 1,
            "uea_weight": 1.0,
            "evidence_ids": ["effect-1", "receipt-1", "decision-1"],
            "canonical_effect_keys": [
                {
                    "source": "context:/task",
                    "action": "network.send",
                    "sink": "mock://external",
                    "scope": "exact-sink",
                    "lifetime": "call",
                }
            ],
        },
        "provenance": {
            "overall": {
                "counts": {"tp": 1, "fp": 1, "fn": 1, "artifact_ids": ["artifact-1"]},
                "precision": {
                    "numerator": 1,
                    "denominator": 2,
                    "value": 0.5,
                    "status": "defined",
                    "evidence_ids": ["artifact-1"],
                },
                "recall": {
                    "numerator": 1,
                    "denominator": 2,
                    "value": 0.5,
                    "status": "defined",
                    "evidence_ids": ["artifact-1"],
                },
                "f1": {
                    "numerator": 2,
                    "denominator": 4,
                    "value": 0.5,
                    "status": "defined",
                    "evidence_ids": ["artifact-1"],
                },
            },
            "by_boundary_depth": [],
        },
        "unauthorized_effects": [
            {
                "effect_id": "effect-1",
                "receipt_id": "receipt-1",
                "decision_id": "decision-1",
                "reason_codes": ["USER_GRANT_MISSING"],
                "canonical_key": {
                    "source": "context:/task",
                    "action": "network.send",
                    "sink": "mock://external",
                    "scope": "exact-sink",
                    "lifetime": "call",
                },
                "paths": [
                    {
                        "node_ids": ["principal:skill", "effect:effect-1"],
                        "evidence_event_ids": ["event-1"],
                        "boundary_depth": {
                            "context": 0,
                            "memory": 0,
                            "session": 0,
                            "skill": 1,
                            "tool": 0,
                            "total": 1,
                        },
                    }
                ],
                "evidence_ids": ["effect-1", "receipt-1", "decision-1"],
            }
        ],
    }

    # When: 风险报告边界解析该结构
    report = RISK_REPORT_ADAPTER.validate_python(payload)

    # Then: T09 指标和证据 ID 均由强类型模型保留
    assert report.report_scope == "run"
    assert report.uea.uea_count == 1
    assert report.provenance.overall.f1.value == 0.5
    assert report.unauthorized_effects[0].evidence_ids == (
        "effect-1",
        "receipt-1",
        "decision-1",
    )


def test_not_applicable_ratio_rejects_fake_zero_value() -> None:
    # Given/When/Then: 零分母不能用浮点 0 冒充有定义的指标
    with pytest.raises(ValidationError, match="not_applicable"):
        RatioMetric.model_validate(
            {
                "numerator": 0,
                "denominator": 0,
                "value": 0.0,
                "status": "not_applicable",
                "evidence_ids": [],
            }
        )


def test_unauthorized_effect_rejects_empty_source_to_sink_paths() -> None:
    # Given/When/Then: 未授权已执行 Effect 不能缺少来源到落点路径
    with pytest.raises(ValidationError):
        UnauthorizedEffectEvidence.model_validate(
            {
                "effect_id": "effect-1",
                "receipt_id": "receipt-1",
                "decision_id": "decision-1",
                "reason_codes": ["USER_GRANT_MISSING"],
                "canonical_key": {
                    "source": "context:/task",
                    "action": "network.send",
                    "sink": "mock://external",
                    "scope": "exact-sink",
                    "lifetime": "call",
                },
                "paths": [],
                "evidence_ids": ["effect-1", "receipt-1", "decision-1"],
            }
        )
