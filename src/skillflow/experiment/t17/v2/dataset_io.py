"""标准数据集导出；全部 CSV 都从结构化报告机械派生。"""

from pathlib import Path

from skillflow.experiment.t17.v2.csv_export import comparison_rows, metric_rows
from skillflow.experiment.t17.v2.csv_models import ComparisonCsvRow, MetricCsvRow
from skillflow.experiment.t17.v2.dataset_analysis import dataset_reports
from skillflow.experiment.t17.v2.dataset_models import DatasetManifest, DatasetStage
from skillflow.experiment.t17.v2.dataset_projection import (
    effect_rows,
    provenance_rows,
    task_rows,
    usage_rows,
)
from skillflow.experiment.t17.v2.dataset_reading import load_dataset
from skillflow.experiment.t17.v2.dataset_reports_io import write_reports
from skillflow.experiment.t17.v2.dataset_rows import (
    ApiUsageRow,
    CoreRow,
    EffectReceiptRow,
    HashManifest,
    ProvenanceRow,
    ReplayRow,
    TaskEvidenceRow,
)
from skillflow.experiment.t17.v2.dataset_writing import DatasetWriter
from skillflow.experiment.t17.v2.loaded_models import LoadedStage
from skillflow.experiment.t17.v2.phase_validation import validate_structured_stage

__all__ = ["export_dataset", "load_dataset"]


def export_dataset(root: Path, output: Path, stages: tuple[LoadedStage, ...]) -> DatasetManifest:
    """只导出本轮实际提供的阶段，绝不拼接同阶段的不同尝试。"""
    if not stages or any(s.configuration != stages[0].configuration for s in stages):
        raise ValueError("v2_dataset_configuration_mismatch")
    for stage in stages:
        validate_structured_stage(stage)
    reports = dataset_reports(stages)
    writer = DatasetWriter(root, output)
    writer.model("skill-catalog.json", stages[0].configuration.catalog)
    writer.rows(
        "core-trials.jsonl",
        (CoreRow.from_terminal(c) for s in stages for c in s.result.cores),
        CoreRow,
    )
    writer.rows(
        "replay-pairs.jsonl",
        (ReplayRow.from_terminal(r) for s in stages for r in s.result.replays),
        ReplayRow,
    )
    writer.rows("task-success-evidence.jsonl", task_rows(stages), TaskEvidenceRow)
    writer.rows("effect-receipts.jsonl", effect_rows(stages), EffectReceiptRow)
    writer.rows("provenance-edges.jsonl", provenance_rows(stages), ProvenanceRow)
    writer.rows("api-usage.jsonl", usage_rows(stages), ApiUsageRow)
    write_reports(writer, "reports.json", reports)
    writer.csv("metrics-long.csv", metric_rows(reports), MetricCsvRow)
    writer.csv("condition-summary.csv", metric_rows(reports, "condition"), MetricCsvRow)
    writer.csv("skill-comparison-ready.csv", metric_rows(reports, "skill"), MetricCsvRow)
    for kind in ("model", "defense", "skill"):
        writer.csv(kind + "-comparison.csv", comparison_rows(reports, kind), ComparisonCsvRow)
    writer.text("README.md", _readme(stages))
    writer.schema_for(DatasetManifest)
    writer.schema_for(HashManifest)
    manifest = DatasetManifest(
        dataset_id=stages[0].configuration.protocol_id + "-structured",
        protocol_id=stages[0].configuration.protocol_id,
        stages=tuple(
            DatasetStage(
                configuration=s.configuration,
                matrix=s.matrix,
                phase=s.result.phase,
                source_phases=s.result.source_phases,
                gate=s.result.gate,
                raw_relative_path=s.raw_relative_path,
                raw_manifest=s.raw_manifest,
                raw_files=s.raw_files,
            )
            for s in stages
        ),
        files=dict(writer.files),
        tables=dict(writer.tables),
        scheduled_core=sum(s.result.phase.scheduled_core for s in stages),
        scheduled_replay=sum(s.result.phase.scheduled_replay for s in stages),
        all_provided_stages_passed=all(s.result.gate.passed for s in stages)
        and all(v.required_metrics_complete for v in reports.vectors),
        contains_live_data=any(s.result.phase.domain == "live_reference" for s in stages),
    )
    writer.model("dataset-manifest.json", manifest)
    writer.model(
        "sha256-manifest.json",
        HashManifest(files={name: item.content for name, item in writer.files.items()}),
    )
    return manifest


def _readme(stages: tuple[LoadedStage, ...]) -> str:
    rows = "\n".join(
        f"| {s.result.phase.stage.value} | {s.result.phase.domain} | "
        f"{len(s.result.cores)} | {len(s.result.replays)} |"
        for s in stages
    )
    return (
        "# T17 第二版：可复算数据\n\n"
        "本目录只描述实际提供的阶段，不代表完整项目已验收。固定脚本、模拟客户端和真实模型分开，不把旧尝试补入分母。\n\n"
        "| 阶段 | 执行域 | 核心任务 | 成对重放 |\n|---|---|---:|---:|\n" + rows + "\n\n"
        "核心表保存全部结构化原始事实及投影哈希；重放表保存同一保存点与两个分支。任务、效果回执和来源表由这些事实派生。每行有技能、版本哈希、模型、模式、表述和重复身份。来源表按输出值列出全部父边；分支前缀效果有单独标记，不能重复当成核心效果。\n\n"
        "JSON 是完整结果，CSV 保留两侧分子、分母、状态、证据与区间。"
        "大表按完整记录分卷，每卷不超过 16 MiB；dataset-manifest.json 的 tables 字段登记整表顺序。"
        "reports.json 索引全部报告分卷。分析入口读取所有分卷，不仅仅读取首卷。"
        "空比较文件表示尚未提供对应阶段，不是第二模型或防御结果为零。"
        "技能家族仅作索引；没有开展多攻击技能实证排名。\n\n"
        "重算使用 `skillflow t17 v2 report --dataset <本目录> --output <新目录>`；"
        "技能比较使用 `skillflow compare-skills --dataset <本目录> --output <新目录>`。"
        "只读原目录，先查哈希，再重算全部投影、报告与表格，不需要私有模型正文或密钥。\n\n"
        "统计以预定任务为主。重复属于表述簇内部，区间使用固定种子 17017、"
        "10000 次簇重抽样；单簇只给描述性点值。Wilson 为链级描述性区间；"
        "区间跨零写不确定，相同点值不证明统计等价。"
        "去重可达集合计数未预注册抽样推断，其区间不适用。\n\n"
        "完整原始记录仍留在清单列明的项目相对目录，全部文件哈希和记录数均保留。"
        "没有模型正文、请求头、真实密钥或宿主绝对路径。"
        "哈希清单自身由外层交付清单登记，不能自哈希。费用为按冻结费率估算，不是账单。"
        "独立审查仍记 REVIEW_UNAVAILABLE。\n"
    )
