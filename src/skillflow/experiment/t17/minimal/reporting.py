"""从不可变最小 Raw 复算并输出单域完整指标。"""

import csv
from pathlib import Path

from skillflow.experiment.t17.contracts import MeasurementStatus, RatioMeasurement
from skillflow.experiment.t17.metric_statistics import wilson_interval
from skillflow.experiment.t17.minimal.artifacts import (
    file_digest,
    model_digest,
    verify_raw_manifest,
    write_checked_json,
)
from skillflow.experiment.t17.minimal.causal_metrics import causal_metrics
from skillflow.experiment.t17.minimal.core_metrics import core_metrics, run_metrics
from skillflow.experiment.t17.minimal.defense_metrics import defense_metrics
from skillflow.experiment.t17.minimal.efficiency_metrics import efficiency_metrics
from skillflow.experiment.t17.minimal.provenance_metrics import provenance_metrics
from skillflow.experiment.t17.minimal.raw_loader import load_minimal_domain
from skillflow.experiment.t17.minimal.report_models import (
    COVERAGE_METRICS,
    MinimalDomainReport,
    MinimalMeasurement,
)
from skillflow.experiment.t17.minimal.schema_models import static_model_validator

_INTERVAL_METRICS = (
    "task_success",
    "safe_task_success",
    "verified_target_effect",
    "uea_affected_trial_rate",
)


def build_minimal_report(root: Path, project_root: Path = Path()) -> MinimalDomainReport:
    """所有原始证据、调度和复算通过后才能生成 measured。"""
    data = load_minimal_domain(root, project_root)
    run_index = {item.run_id: item for item in data.runs}
    per_run = {
        item.run_id: {
            **run_metrics(item, run_index[item.run_id]),
            **provenance_metrics((run_index[item.run_id].provenance,)),
        }
        for item in data.records
    }
    metrics = {
        **core_metrics(data),
        **provenance_metrics(tuple(item.provenance for item in data.runs)),
        **causal_metrics(data, root, project_root),
        **efficiency_metrics(data),
    }
    defense = defense_metrics(data, per_run)
    verify_raw_manifest(root, data.manifest)
    return MinimalDomainReport(
        domain=data.phase.domain,
        technical_gate_passed=_gate(metrics, defense),
        observed_core_runs=len(data.runs),
        observed_replay_pairs=len(data.replays),
        phase_contract_sha256=model_digest(data.phase),
        raw_manifest_sha256=file_digest(root / "raw-manifest.json"),
        configuration_sha256=data.phase.configuration_sha256,
        matrix_sha256=data.phase.matrix_sha256,
        run_ids=tuple(item.run_id for item in data.runs),
        replay_ids=tuple(item.replay_id for item in data.replays),
        metrics=metrics,
        defense=defense,
        per_run=per_run,
        wilson_intervals={key: wilson_interval(_ratio(metrics[key])) for key in _INTERVAL_METRICS},
        qualifications=(
            "仅为受控 Scripted/Fake Reference Harness 技术测量链，不代表真实模型或生产 OpenClaw。",
            (
                "Task Success evaluator 2.0.0 与旧风险 Golden 独立；"
                "旧 Raw 与 evaluator 1.0.0 不回填、不合并。"
            ),
            (
                "scheduled core 是主分母；valid-only 只作 HIAA 敏感性分析，"
                "Replay 不进入普通 core 分母。"
            ),
            "HIAA potential 沿用现有观察到的可达未授权 Effect 集合定义，不声称枚举全部潜在执行。",
            (
                "ALR baseline reason 由实际请求、Grant、决策依据和冻结规则重建；"
                "不是模型自报或配置标签。"
            ),
            "UEA weight 沿用现有默认 w(e)=1，等于实例数；不是 sensitivity 加权或总安全分。",
            "单实例区间仅为 Wilson 链级描述性区间，不作跨语义实例推断或显著性结论。",
            "防御仅复用 B0/B1 的最小合法与风险配对；未对其他场景扩展防御实验。",
            "此处 technical_gate 只表示单域测量链完整；全量测试、独立审查与项目最终验收另行登记。",
        ),
    )


def write_minimal_report(
    root: Path, output: Path, project_root: Path = Path()
) -> MinimalDomainReport:
    """新报告写在 Raw 根之外，拒绝覆盖任何已有输出。"""
    if output.resolve().is_relative_to(root.resolve()):
        raise ValueError("minimal_report_cannot_mutate_raw")
    if output.exists() or output.with_suffix(".csv").exists():
        raise ValueError("minimal_report_output_exists")
    report = build_minimal_report(root, project_root)
    static_model_validator(MinimalDomainReport).validate(report.model_dump(mode="json"))
    write_checked_json(output, report)
    with output.with_suffix(".csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "domain",
                "group",
                "metric",
                "status",
                "numerator",
                "denominator",
                "value",
                "unit",
                "denominator_scope",
                "reason",
                "evidence_ids",
            )
        )
        for group, values in (("metrics", report.metrics), ("defense", report.defense)):
            for name, metric in sorted(values.items()):
                writer.writerow(
                    (
                        report.domain,
                        group,
                        name,
                        metric.status.value,
                        metric.numerator,
                        metric.denominator,
                        metric.value,
                        metric.unit,
                        metric.denominator_scope,
                        metric.reason,
                        "|".join(metric.evidence_ids),
                    )
                )
    return report


def _gate(metrics: dict[str, MinimalMeasurement], defense: dict[str, MinimalMeasurement]) -> bool:
    return all(metrics[name].value == 1 for name in COVERAGE_METRICS) and all(
        item.status in {MeasurementStatus.MEASURED, MeasurementStatus.NOT_APPLICABLE}
        for item in (*metrics.values(), *defense.values())
    )


def _ratio(value: MinimalMeasurement) -> RatioMeasurement:
    if not isinstance(value.numerator, int) or not isinstance(value.denominator, int):
        raise TypeError("minimal_wilson_requires_integer_counts")
    return RatioMeasurement(
        status=value.status,
        numerator=value.numerator,
        denominator=value.denominator,
        value=value.value,
        evidence_ids=value.evidence_ids,
    )
