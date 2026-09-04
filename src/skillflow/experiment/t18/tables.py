"""从现有公开事实导出计划要求的九种明细，不触发实验或修改规则。"""

import csv
import hashlib
import io
import json
from collections.abc import Iterable
from pathlib import Path

from skillflow.defense.models import DefenseOutcome
from skillflow.experiment.t17.v2.canonical import canonical_text
from skillflow.experiment.t18.dataset import REPORT_FILES, load_dataset
from skillflow.experiment.t18.metric_models import Measure
from skillflow.experiment.t18.report_data import AnalysisData, validate_data
from skillflow.experiment.t18.reporting import LocalReport, build_report, write_report
from skillflow.experiment.t18.run_models import LocalCore
from skillflow.experiment.t18.table_models import (
    DiagnosisRow,
    OutcomeRow,
    PlanRow,
    TableFile,
    TableManifest,
)
from skillflow.models.base import StrictModel

TABLE_NAMES = (
    "core-trials.jsonl",
    "replay-pairs.jsonl",
    "diagnoses.jsonl",
    "defense-plans.jsonl",
    "defense-outcomes.jsonl",
    "diagnosis-metrics.json",
    "defense-specificity.csv",
    "router-comparison.csv",
    "skill-metrics.csv",
)


def _jsonl(rows: Iterable[StrictModel]) -> tuple[str, int]:
    values = tuple(canonical_text(row) for row in rows)
    return "".join(value + "\n" for value in values), len(values)


def _csv(groups: Iterable[tuple[str, str, dict[str, Measure]]]) -> tuple[str, int]:
    table = io.StringIO(newline="")
    writer = csv.writer(table, lineterminator="\n")
    writer.writerow(
        (
            "domain",
            "group",
            "metric",
            "status",
            "numerator",
            "denominator",
            "value",
            "reason",
            "interval_status",
            "interval_reason",
            "evidence_ids",
        )
    )
    count = 0
    for domain, group, values in groups:
        for name, metric in sorted(values.items()):
            writer.writerow(
                (
                    domain,
                    group,
                    name,
                    metric.status,
                    metric.numerator,
                    metric.denominator,
                    metric.value,
                    metric.reason,
                    metric.interval_status,
                    metric.interval_reason,
                    json.dumps(metric.evidence_ids, ensure_ascii=False),
                )
            )
            count += 1
    return table.getvalue(), count


def _outcome(before: LocalCore, after: LocalCore) -> DefenseOutcome:
    if before.data is None or after.data is None:
        raise ValueError("t18_outcome_incomplete")
    sources = (before.data, after.data)
    effects = tuple(tuple(e for e in source.facts.effects if e.executed) for source in sources)
    decisions = tuple(
        {d.decision_id: d.authorized for d in source.facts.decisions} for source in sources
    )
    baseline, task = before.data.proof.task, after.data.proof.task
    evidence = tuple(
        dict.fromkeys(
            (
                before.run_id,
                after.run_id,
                *baseline.evidence_ids,
                *task.evidence_ids,
                *(e.effect_id for group in effects for e in group),
                *(e.tool_receipt_id for group in effects for e in group if e.tool_receipt_id),
            )
        )
    )
    return DefenseOutcome(
        outcome_id="t18-outcome:" + before.run_id + ":" + after.run_id,
        before_run_id=before.run_id,
        after_run_id=after.run_id,
        before_effect_ids=tuple(e.effect_id for e in effects[0]),
        after_effect_ids=tuple(e.effect_id for e in effects[1]),
        before_authorization=tuple(decisions[0][e.decision_id] for e in effects[0]),
        after_authorization=tuple(decisions[1][e.decision_id] for e in effects[1]),
        task_success=task.task_success,
        safe_task_success=task.safe_task_success,
        utility_loss=int(baseline.task_success) - int(task.task_success),
        over_defense=(
            before.cell.role != "attack" and baseline.task_success and not task.task_success
        ),
        residual_risk=bool(task.risk_effect_ids),
        actual_extra_steps=sum(t.extra_steps for t in after.traces),
        actual_latency_ms=after.latency_ms,
        evidence_ids=evidence,
    )


def _outcomes(data: AnalysisData, report: LocalReport) -> Iterable[OutcomeRow]:
    by_run = {c.run_id: c for c in data.cores}
    for comparison in report.comparisons:
        for left, right in comparison.pair_run_ids:
            before, after = by_run[left], by_run[right]
            yield OutcomeRow(
                domain=data.phase.domain,
                comparison_id=comparison.comparison_id,
                before_trial_id=before.cell.trial_id,
                after_trial_id=after.cell.trial_id,
                outcome=_outcome(before, after),
            )


def _payloads(data: tuple[AnalysisData, ...]) -> dict[str, tuple[str, int]]:
    cores = tuple(core for group in data for core in group.cores)
    reports = tuple(build_report(group) for group in data)
    diagnoses = (
        DiagnosisRow(
            domain=core.domain,
            trial_id=core.cell.trial_id,
            run_id=core.run_id,
            request_event_id=trace.request_event_id,
            signals=trace.signals,
            diagnosis=trace.diagnosis,
        )
        for core in cores
        for trace in core.traces
    )
    plans = (
        PlanRow(
            domain=core.domain,
            trial_id=core.cell.trial_id,
            run_id=core.run_id,
            request_event_id=trace.request_event_id,
            proposed_plan=trace.proposed_plan,
            actual_defense_ids=trace.selected,
            authorized=trace.final_authorized,
            executed=trace.final_executed,
            actual_extra_steps=trace.extra_steps,
        )
        for core in cores
        for trace in core.traces
    )
    diagnosis_metrics = {
        report.domain: {
            group: {
                name: metric.model_dump(mode="json")
                for name, metric in sorted(values.items())
                if name.startswith("diagnosis.")
            }
            for group, values in sorted(report.vectors.items())
        }
        for report in reports
    }
    return {
        "core-trials.jsonl": _jsonl(cores),
        "replay-pairs.jsonl": _jsonl(pair for group in data for pair in group.replays),
        "diagnoses.jsonl": _jsonl(diagnoses),
        "defense-plans.jsonl": _jsonl(plans),
        "defense-outcomes.jsonl": _jsonl(
            row
            for group, report in zip(data, reports, strict=True)
            for row in _outcomes(group, report)
        ),
        "diagnosis-metrics.json": (
            json.dumps(diagnosis_metrics, ensure_ascii=False, indent=2) + "\n",
            sum(len(values) for domain in diagnosis_metrics.values() for values in domain.values()),
        ),
        "defense-specificity.csv": _csv(
            (report.domain, group, values)
            for report in reports
            for group, values in sorted(report.specificity.items())
        ),
        "router-comparison.csv": _csv(
            (report.domain, comparison.comparison_id, comparison.metrics)
            for report in reports
            for comparison in report.comparisons
        ),
        "skill-metrics.csv": _csv(
            (report.domain, group, values)
            for report in reports
            for group, values in sorted(report.vectors.items())
            if group.startswith("skill.")
        ),
    }


def _write(path: Path, content: str) -> None:
    if path.exists():
        if path.read_bytes() != content.encode("utf-8"):
            raise ValueError("t18_table_existing_content_differs:" + path.name)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def write_tables(data: tuple[AnalysisData, ...], output: Path) -> TableManifest:
    """只投影已完成、已绑定的原始事实；已有文件只允许完全相同。"""
    if not data or len({group.phase.domain for group in data}) != len(data):
        raise ValueError("t18_tables_duplicate_or_empty_domains")
    for group in data:
        if not group.complete:
            raise ValueError("t18_tables_incomplete")
        validate_data(group, verify=False)
    ordered = tuple(sorted(data, key=lambda group: group.phase.domain))
    files = {}
    for name, (content, records) in _payloads(ordered).items():
        _write(output / name, content)
        encoded = content.encode("utf-8")
        files[name] = TableFile(
            sha256=hashlib.sha256(encoded).hexdigest(), bytes=len(encoded), records=records
        )
    manifest = TableManifest(
        domains=tuple(group.phase.domain for group in ordered),
        source_phase_contracts={
            group.phase.domain: group.cores[0].phase_contract_sha256 for group in ordered
        },
        files=files,
    )
    _write(output / "sha256-manifest.json", manifest.model_dump_json(indent=2) + "\n")
    return manifest


def recompute_collection(directory: Path, output: Path) -> dict[str, str | int]:
    """仅从公开集合复算两个域和交付明细，不读取私有目录。"""
    if output.resolve().is_relative_to(directory.resolve()):
        raise ValueError("t18_recompute_requires_separate_output")
    expected = TableManifest.model_validate_json(
        (directory / "sha256-manifest.json").read_text(encoding="utf-8")
    )
    data = tuple(load_dataset(directory / domain) for domain in expected.domains)
    manifest = write_tables(data, output)
    if manifest != expected:
        raise ValueError("t18_collection_manifest_mismatch")
    names = [*TABLE_NAMES, "sha256-manifest.json"]
    for group in data:
        target = Path(group.phase.domain) / "reports"
        write_report(output / target, build_report(group))
        names.extend((target / name).as_posix() for name in REPORT_FILES)
    for name in names:
        if (output / name).read_bytes() != (directory / name).read_bytes():
            raise ValueError("t18_collection_recompute_mismatch:" + name)
    result: dict[str, str | int] = {
        "status": "pass",
        "domains": len(data),
        "core_count": sum(len(group.cores) for group in data),
        "replay_pairs": sum(len(group.replays) for group in data),
        "compared_files": len(names),
        "api_calls": 0,
    }
    _write(output / "recompute-status.json", json.dumps(result, indent=2) + "\n")
    return result
