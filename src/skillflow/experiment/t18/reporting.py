"""完整 T18 指标表：全部调度、同模式、留出、技能和四格分别呈现。"""

import csv
import io
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from skillflow.experiment.t18.causal_metrics import causal_metrics
from skillflow.experiment.t18.comparisons import DefenseComparison, compare
from skillflow.experiment.t18.core_metrics import core_metrics
from skillflow.experiment.t18.diagnosis_metrics import diagnosis_metrics
from skillflow.experiment.t18.hiaa import HiaaReport, compute_hiaa
from skillflow.experiment.t18.matrix import MODES, CoreCell, Mode
from skillflow.experiment.t18.metric_models import Measure
from skillflow.experiment.t18.report_data import AnalysisData, hiaa_trials
from skillflow.models.base import NonEmptyStr, StrictModel


class LocalReport(StrictModel):
    """不同域从不合并；单簇点值不附会总体显著性。"""

    schema_version: Literal["18.0"] = "18.0"
    domain: NonEmptyStr
    status: Literal["measured", "incomplete"]
    scheduled_core: int
    completed_core: int
    replay_pairs: int
    vectors: dict[NonEmptyStr, dict[NonEmptyStr, Measure]]
    hiaa: tuple[HiaaReport, ...]
    comparisons: tuple[DefenseComparison, ...]
    specificity: dict[NonEmptyStr, dict[NonEmptyStr, Measure]]
    regret_weights: dict[NonEmptyStr, float]
    population_note: str = (
        "全部调度单列；主比较限桥梁开启，四格补充单元只进入对应四格与全部调度表。"
        "模拟域各模式样本不齐时只做交集配对。"
    )


def build_report(data: AnalysisData) -> LocalReport:
    """纯事实到指标，分组可以用标签，数值只读原始证据。"""
    primary = data.select(lambda c: c.bridge_enabled)
    groups = {"all_scheduled": data, "primary_on": primary}
    for mode in MODES:
        selected = primary.select(_condition(mode=mode))
        if selected.scheduled:
            groups["mode." + mode] = selected
            groups["development." + mode] = selected.select(lambda c: c.split == "development")
            groups["held_out." + mode] = selected.select(lambda c: c.split == "held-out")
    for skill in data.catalog.skills:
        for mode in MODES:
            selected = primary.select(_condition(mode=mode, skill_id=skill.skill_variant_id))
            if selected.scheduled:
                groups["skill." + skill.skill_variant_id + "." + mode] = selected
    vectors = {key: _vector(group) for key, group in groups.items() if group.scheduled}
    comparisons = tuple(
        compare(primary, "monitor", mode)
        for mode in MODES
        if mode != "monitor" and any(c.mode == mode for c in primary.scheduled)
    )
    comparisons += (compare(primary, "oracle_router", "evidence_router"),)
    specificity = {}
    for base in sorted({c.base_id for c in primary.scheduled if c.role == "attack"}):
        selected = primary.select(_condition(base=base)).select(lambda c: c.role == "attack")
        for mode in ("task_alignment_only", "tdg_only", "drift_isolation_only", "causal_only"):
            if any(c.mode == mode for c in selected.scheduled):
                specificity[base + "." + mode] = compare(selected, "monitor", mode).metrics
    hiaa = compute_hiaa(data.matrix, hiaa_trials(data))
    complete = (
        data.complete
        and all(r.status == "measured" for r in hiaa)
        and all(
            v.status not in {"not_available", "incomplete"}
            for values in vectors.values()
            for v in values.values()
        )
    )
    return LocalReport(
        domain=data.phase.domain,
        status="measured" if complete else "incomplete",
        scheduled_core=len(data.scheduled),
        completed_core=len(data.cores),
        replay_pairs=len(data.replays),
        vectors=vectors,
        hiaa=hiaa,
        comparisons=comparisons,
        specificity=specificity,
        regret_weights=data.config.regret_weights,
    )


def _vector(data: AnalysisData) -> dict[str, Measure]:
    metrics = core_metrics(data)
    metrics.update(causal_metrics(data))
    metrics.update({"diagnosis." + k: v for k, v in diagnosis_metrics(data).items()})
    return metrics


def _condition(
    *, mode: Mode | None = None, skill_id: str | None = None, base: str | None = None
) -> Callable[[CoreCell], bool]:
    return lambda c: (
        (mode is None or c.mode == mode)
        and (skill_id is None or c.skill_variant_id == skill_id)
        and (base is None or c.base_id == base)
    )


def write_report(directory: Path, report: LocalReport) -> None:
    """正式 JSON 与 CSV 同源生成，已有不同内容拒绝覆盖。"""
    directory.mkdir(parents=True, exist_ok=True)
    _write(directory / "metrics.json", report.model_dump_json(indent=2) + "\n")
    table = io.StringIO(newline="")
    writer = csv.writer(table, lineterminator="\n")
    writer.writerow(
        ("domain", "group", "metric", "status", "numerator", "denominator", "value", "reason")
    )
    for vector_id, values in sorted(report.vectors.items()):
        for name, m in sorted(values.items()):
            writer.writerow(
                (
                    report.domain,
                    vector_id,
                    name,
                    m.status,
                    m.numerator,
                    m.denominator,
                    m.value,
                    m.reason,
                )
            )
    for comparison in report.comparisons:
        for name, m in sorted(comparison.metrics.items()):
            writer.writerow(
                (
                    report.domain,
                    "comparison." + comparison.comparison_id,
                    name,
                    m.status,
                    m.numerator,
                    m.denominator,
                    m.value,
                    m.reason,
                )
            )
    _write(directory / "summary.csv", table.getvalue())
    table = io.StringIO(newline="")
    writer = csv.writer(table, lineterminator="\n")
    writer.writerow(
        (
            "domain",
            "design",
            "mode",
            "cell",
            "population",
            "status",
            "numerator",
            "denominator",
            "value",
            "refusal",
            "no_call",
            "schema_failure",
            "task_failure",
        )
    )
    for group in report.hiaa:
        for name, cell in sorted(group.cells.items()):
            for population, rate in (
                ("scheduled", cell.scheduled),
                ("valid_only", cell.valid_only),
            ):
                writer.writerow(
                    (
                        report.domain,
                        group.design_id,
                        group.mode,
                        name,
                        population,
                        rate.status,
                        rate.numerator,
                        rate.denominator,
                        rate.value,
                        *(
                            cell.failures[k]
                            for k in ("refusal", "no_call", "schema_failure", "task_failure")
                        ),
                    )
                )
        for name, value in (
            ("hiaa_scheduled", group.scheduled),
            ("hiaa_valid_only", group.valid_only),
            ("delta_hiaa", group.delta_hiaa),
            ("delta_hiaa_valid_only", group.delta_hiaa_valid_only),
        ):
            writer.writerow(
                (
                    report.domain,
                    group.design_id,
                    group.mode,
                    "contrast",
                    name,
                    value.status,
                    "",
                    "",
                    value.value,
                    "",
                    "",
                    "",
                    "",
                )
            )
    _write(directory / "hiaa.csv", table.getvalue())


def _write(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError("t18_report_existing_content_differs:" + path.name)
        return
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
