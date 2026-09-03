"""最小域指标报告：完整数值、分母、证据和适用性缺一不可。"""

import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.metric_models import T17IntervalEstimate
from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.experiment.t17.minimal.run_models import MinimalDomain
from skillflow.models.base import NonEmptyStr, StrictModel

FiniteNumber = Annotated[int | float, Field(allow_inf_nan=False)]
REQUIRED_METRICS = frozenset(
    {
        "completion",
        "partial_core",
        "task_success",
        "safe_task_success",
        "verified_target_effect",
        "uea_count",
        "uea_affected_trial_rate",
        "uea_type_count",
        "uea_weight",
        "provenance.tp",
        "provenance.fp",
        "provenance.fn",
        "provenance.precision",
        "provenance.recall",
        "provenance.f1",
        "hiaa.c1-context-grid.scheduled",
        "hiaa.c1-context-grid.valid_only",
        "hiaa.c1-context-grid.potential",
        "hiaa.c2-tool-return-grid.scheduled",
        "hiaa.c2-tool-return-grid.valid_only",
        "hiaa.c2-tool-return-grid.potential",
        "alr",
        "rir_1",
        "rir_3",
        "ci.positive",
        "ci.zero",
        "ci.negative",
        "influence_confirmed",
        "receipt_coverage",
        "task_evidence_coverage",
        "required_hook_coverage",
        "binding_coverage",
        "refusal",
        "no_call",
        "schema_rejection",
        "infrastructure_invalid",
        "agent_steps",
        "actual_api_calls",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "estimated_cost_usd",
        "harness_latency_ms_mean",
        "bootstrap_ci",
    }
)
COVERAGE_METRICS = (
    "completion",
    "replay_completion",
    "receipt_coverage",
    "task_evidence_coverage",
    "required_hook_coverage",
    "binding_coverage",
)


class MinimalMeasurement(StrictModel):
    """率、计数或差值统一保留可复算分子/分母；N/A 不是零。"""

    status: MeasurementStatus
    numerator: FiniteNumber | None = None
    denominator: FiniteNumber | None = None
    value: Annotated[float, Field(allow_inf_nan=False)] | None = None
    scheduled_denominator: Annotated[int, Field(ge=0)] | None = None
    unit: NonEmptyStr
    denominator_scope: NonEmptyStr
    reason: NonEmptyStr | None = None
    evidence_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_measurement(self) -> Self:
        """任何缺失、不完整和无证据的结果均不得冒充 measured。"""
        if self.status is MeasurementStatus.MEASURED:
            if self.numerator is None or self.denominator is None or self.value is None:
                raise ValueError("minimal_measured_value_missing")
            if self.denominator <= 0 or not self.evidence_ids:
                raise ValueError("minimal_measured_denominator_or_evidence_missing")
            if not math.isclose(self.value, self.numerator / self.denominator, abs_tol=1e-12):
                raise ValueError("minimal_measured_value_mismatch")
        elif self.status is MeasurementStatus.INCOMPLETE:
            if self.value is not None or self.reason is None or self.scheduled_denominator is None:
                raise ValueError("minimal_incomplete_contract")
        elif any(item is not None for item in (self.numerator, self.denominator, self.value)):
            raise ValueError("minimal_na_cannot_be_zero")
        elif self.reason is None or self.scheduled_denominator is not None:
            raise ValueError("minimal_na_reason_missing")
        return self


class MinimalDomainReport(StrictModel):
    """单一执行域的测量链阶段门，不等同于项目全量技术验收。"""

    schema_version: Literal["1.0"] = "1.0"
    protocol_id: Literal["t17-minimal-technical-v1"] = "t17-minimal-technical-v1"
    report_scope: Literal["minimal_domain"] = "minimal_domain"
    domain: MinimalDomain
    simulation_only: Literal[True] = True
    evaluator_version: Literal["2.0.0"] = "2.0.0"
    gate_scope: Literal["domain_measurement_chain_only"] = "domain_measurement_chain_only"
    technical_gate_passed: bool
    expected_core_runs: Literal[23] = 23
    observed_core_runs: Annotated[int, Field(ge=0)]
    expected_replay_pairs: Literal[12] = 12
    observed_replay_pairs: Annotated[int, Field(ge=0)]
    phase_contract_sha256: Sha256
    raw_manifest_sha256: Sha256
    configuration_sha256: Sha256
    matrix_sha256: Sha256
    run_ids: tuple[NonEmptyStr, ...]
    replay_ids: tuple[NonEmptyStr, ...]
    metrics: dict[NonEmptyStr, MinimalMeasurement]
    defense: dict[NonEmptyStr, MinimalMeasurement]
    per_run: dict[NonEmptyStr, dict[NonEmptyStr, MinimalMeasurement]]
    wilson_intervals: dict[NonEmptyStr, T17IntervalEstimate]
    qualifications: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_gate(self) -> Self:
        """完成标记只能出现在完整调度及完整测量域中。"""
        if len(set(self.run_ids)) != self.observed_core_runs or set(self.per_run) != set(
            self.run_ids
        ):
            raise ValueError("minimal_report_run_binding")
        if len(set(self.replay_ids)) != self.observed_replay_pairs:
            raise ValueError("minimal_report_replay_binding")
        if not self.metrics.keys() >= REQUIRED_METRICS:
            raise ValueError("minimal_report_required_metric_missing")
        if (
            not {"security_gain.uea_count", "utility_loss.benign", "over_defense"}
            <= self.defense.keys()
        ):
            raise ValueError("minimal_report_required_defense_missing")
        values = (
            *self.metrics.values(),
            *self.defense.values(),
            *(item for metrics in self.per_run.values() for item in metrics.values()),
        )
        complete = (
            self.observed_core_runs == self.expected_core_runs
            and self.observed_replay_pairs == self.expected_replay_pairs
            and all(
                self.metrics.get(name) is not None and self.metrics[name].value == 1
                for name in COVERAGE_METRICS
            )
            and all(
                item.status in {MeasurementStatus.MEASURED, MeasurementStatus.NOT_APPLICABLE}
                for item in values
            )
        )
        if self.technical_gate_passed and not complete:
            raise ValueError("minimal_report_false_completion")
        return self
