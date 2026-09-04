"""从报告机械生成可读长表；公式前缀按 CSV 文本安全转义。"""

import csv
import io
import json
from collections.abc import Iterable, Iterator

from pydantic_core import to_jsonable_python

from skillflow.experiment.t17.v2.csv_models import ComparisonCsvRow, MetricCsvRow
from skillflow.experiment.t17.v2.dataset_models import DatasetReports
from skillflow.models.base import StrictModel


def json_cell(value: object) -> str:
    """JSON 串明确表达空集合与缺失值，避免字符串拼接丢身份。"""
    return json.dumps(
        to_jsonable_python(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def metric_rows(reports: DatasetReports, kind: str | None = None) -> Iterator[MetricCsvRow]:
    """按报告顺序输出，每个条件的完整向量都有独立报告身份。"""
    for report in reports.vectors:
        if kind is not None and report.kind != kind:
            continue
        identity = report.identity
        for name, value in sorted(report.metrics.items()):
            yield MetricCsvRow(
                report_id=report.report_id,
                report_kind=report.kind,
                domain=identity.domain,
                requested_model=identity.requested_model,
                model_revision=identity.model_revision,
                stages_json=json_cell(identity.stages),
                conditions_json=json_cell(identity.condition_ids),
                skills_json=json_cell(identity.skill_variant_ids),
                defense_modes_json=json_cell(identity.enforcement_modes),
                phase_contracts_json=json_cell(identity.phase_contract_sha256),
                matrices_json=json_cell(identity.matrix_sha256),
                metric=name,
                status=value.status,
                numerator=value.numerator,
                denominator=value.denominator,
                value=value.value,
                scheduled_denominator=value.scheduled_denominator,
                unit=value.unit,
                denominator_scope=value.denominator_scope,
                complete_clusters=value.complete_clusters,
                intervals_json=json_cell(value.intervals),
                evidence_ids_json=json_cell(value.evidence_ids),
                cluster_terms_json=json_cell(value.cluster_terms),
                contrast_signs_json=json_cell(value.contrast_signs),
                reason=value.reason,
            )


def comparison_rows(reports: DatasetReports, kind: str) -> Iterator[ComparisonCsvRow]:
    """同时保存两侧比例原始字段，零值不与缺测混淆。"""
    for report in reports.comparisons:
        if report.kind != kind:
            continue
        for row in report.comparisons:
            yield ComparisonCsvRow(
                report_id=report.report_id,
                comparison_kind=report.kind,
                metric=row.metric,
                left_identity_json=json_cell(report.left.identity),
                right_identity_json=json_cell(report.right.identity),
                left_value=row.left.value,
                right_value=row.right.value,
                delta_value=row.delta.value,
                delta_status=row.delta.status,
                left_measurement_json=json_cell(row.left),
                right_measurement_json=json_cell(row.right),
                delta_measurement_json=json_cell(row.delta),
                left_point_direction=row.left_point_direction,
                right_point_direction=row.right_point_direction,
                left_interval_direction=row.left_interval_direction,
                right_interval_direction=row.right_interval_direction,
                point_agreement=row.point_agreement,
                interval_agreement=row.interval_agreement,
                complete_clusters=row.delta.complete_clusters,
                named_deltas_json=json_cell(
                    {
                        key: value
                        for key, value in report.named_deltas.items()
                        if key in {"delta." + row.metric, "security_gain." + row.metric}
                        or (
                            row.metric == "task_success" and key in {"utility_loss", "over_defense"}
                        )
                        or (row.metric == "safe_task_success" and key == "safe_task_success_delta")
                    }
                ),
            )


def csv_text(rows: Iterable[StrictModel], columns: tuple[str, ...]) -> tuple[str, int]:
    """空比较仍有表头，表示尚未提供对应阶段而不是测量为零。"""
    lines = tuple(csv_records(rows, columns))
    return csv_header(columns) + "".join(lines), len(lines)


def csv_header(columns: tuple[str, ...]) -> str:
    """每个分卷都具有相同字段名，仍可单独用表格软件打开。"""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    return stream.getvalue()


def csv_records(rows: Iterable[StrictModel], columns: tuple[str, ...]) -> Iterator[str]:
    """每条完整 CSV 记录作为一块，不能在带引号的换行中拆卷。"""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    for row in rows:
        stream.seek(0)
        stream.truncate()
        writer.writerow(csv_fields(row))
        yield stream.getvalue()


def csv_fields(row: StrictModel) -> dict[str, str]:
    """复算校验复用相同文本转义，不把空字段改成零。"""
    return {
        key: "" if value is None else str(_safe_cell(value))
        for key, value in row.model_dump(mode="json").items()
    }


def _safe_cell(value: object) -> object:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value
