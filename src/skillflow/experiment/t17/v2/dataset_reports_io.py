"""报告按完整指标向量或比较分卷，保留每一项证据和区间。"""

from pathlib import Path

from skillflow.experiment.t17.v2.dataset_models import DatasetReports, ReportIndex
from skillflow.experiment.t17.v2.dataset_writing import DatasetWriter
from skillflow.experiment.t17.v2.frozen import inside
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.report_models import ComparisonReport, MetricVectorReport


def write_reports(writer: DatasetWriter, name: str, reports: DatasetReports) -> None:
    """索引和每份完整报告都有独立格式与哈希。"""
    vectors = []
    comparisons = []
    for index, vector in enumerate(reports.vectors, 1):
        path = f"reports/vector-{index:04d}.json"
        writer.model(path, vector)
        vectors.append(path)
    for index, comparison in enumerate(reports.comparisons, 1):
        path = f"reports/comparison-{index:04d}.json"
        writer.model(path, comparison)
        comparisons.append(path)
    writer.model(name, ReportIndex(vectors=tuple(vectors), comparisons=tuple(comparisons)))


def read_reports(root: Path, name: str) -> DatasetReports:
    """缺卷、重复卷或类型错误直接拒绝，不返回部分完整报告。"""
    index = read_model(inside(root, name), ReportIndex)
    names = (*index.vectors, *index.comparisons)
    if len(set(names)) != len(names):
        raise ValueError("v2_report_parts_duplicate")
    return DatasetReports(
        vectors=tuple(read_model(inside(root, p), MetricVectorReport) for p in index.vectors),
        comparisons=tuple(read_model(inside(root, p), ComparisonReport) for p in index.comparisons),
    )
