"""从五个已通过数据集生成完整分层交付；无网络、无原始响应重采。"""

# ruff: noqa: INP001

import argparse
import shutil
from pathlib import Path
from typing import Literal

from t17_collection_binding import ModelPairContract, validate_model_pair

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.comparisons import compare_vectors, defense_comparison
from skillflow.experiment.t17.v2.csv_export import comparison_rows, metric_rows
from skillflow.experiment.t17.v2.csv_models import ComparisonCsvRow, MetricCsvRow
from skillflow.experiment.t17.v2.dataset_models import DatasetFile, DatasetManifest, DatasetReports
from skillflow.experiment.t17.v2.dataset_reading import load_dataset
from skillflow.experiment.t17.v2.dataset_reports_io import read_reports, write_reports
from skillflow.experiment.t17.v2.dataset_rows import HashManifest
from skillflow.experiment.t17.v2.dataset_tables import validate_csv_rows
from skillflow.experiment.t17.v2.dataset_writing import DatasetWriter, guard_public
from skillflow.experiment.t17.v2.frozen import FrozenFile, file_digest, inside, verify_files
from skillflow.experiment.t17.v2.loaded_models import LoadedStage
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.report_models import ComparisonReport, MetricVectorReport
from skillflow.models.base import StrictModel

STAGES = {
    "e": T17LiveStage.CANARY,
    "f": T17LiveStage.MODEL1,
    "g_canary": T17LiveStage.MODEL2_CANARY,
    "g": T17LiveStage.MODEL2,
    "h": T17LiveStage.DEFENSE,
}
DEFENSE_BASE_COUNT = 21


class StageReference(StrictModel):
    """指向逐阶段完整公开数据，原配置和来源身份不变。"""

    directory: str
    original_dataset_directory: str
    manifest: FrozenFile
    scheduled_core: int
    scheduled_replay: int


class CollectionManifest(StrictModel):
    """集合只汇集分层结果，不把不同模型或预检合成总体比例。"""

    schema_version: Literal["t17-collection/1.0"] = "t17-collection/1.0"
    stages: dict[str, StageReference]
    model_pair_contract: ModelPairContract
    files: dict[str, DatasetFile]
    tables: dict[str, tuple[str, ...]]
    scope: Literal["five_passed_stages_and_stratified_comparisons"] = (
        "five_passed_stages_and_stratified_comparisons"
    )
    pooling_allowed: Literal[False] = False
    raw_model_text_included: Literal[False] = False
    independent_review: Literal["REVIEW_UNAVAILABLE"] = "REVIEW_UNAVAILABLE"
    full_project_completion_claim: Literal[False] = False


def read_stages(
    root: Path, paths: dict[str, str]
) -> tuple[
    dict[str, LoadedStage],
    dict[str, DatasetReports],
]:
    """每个阶段从完整事实复算一次；不接受只有百分比的汇总。"""
    if set(paths) != set(STAGES):
        raise ValueError("collection_requires_exact_five_stages")
    stages, reports = {}, {}
    for name, expected_stage in STAGES.items():
        directory = inside(root, paths[name])
        loaded = load_dataset(directory)
        if len(loaded) != 1 or loaded[0].result.phase.stage != expected_stage:
            raise ValueError("collection_stage_identity_mismatch")
        if not loaded[0].result.gate.passed:
            raise ValueError("collection_stage_not_passed")
        stages[name] = loaded[0]
        reports[name] = read_reports(directory, "reports.json")
        print(f"validated: {name}", flush=True)  # noqa: T201
    return stages, reports


def model_reports(left: DatasetReports, right: DatasetReports) -> tuple[ComparisonReport, ...]:
    """只比较正式阶段及各条件，完整性检查由调用方先完成。"""

    def selected(reports: DatasetReports) -> dict[tuple[str, tuple[str, ...]], MetricVectorReport]:
        vectors = tuple(v for v in reports.vectors if v.kind in {"stage", "condition"})
        result: dict[tuple[str, tuple[str, ...]], MetricVectorReport] = {
            (v.kind, v.identity.condition_ids): v for v in vectors
        }
        if len(result) != len(vectors):
            raise ValueError("collection_duplicate_comparison_stratum")
        return result

    lside, rside = selected(left), selected(right)
    if set(lside) != set(rside):
        raise ValueError("collection_missing_model_condition")
    return tuple(
        compare_vectors(
            lside[key],
            rside[key],
            "model1-vs-model2" + ("." + key[1][0] if key[0] == "condition" else ""),
            "model",
        )
        for key in sorted(lside)
    )


def defense_reports(model1: LoadedStage, added: LoadedStage) -> tuple[ComparisonReport, ...]:
    """复用 F 加上 H 的补集；不重复采样或重复计数原有模式。"""
    if model1.configuration != added.configuration:
        raise ValueError("collection_defense_configuration_mismatch")
    group = AnalysisGroup(
        model1.configuration,
        (*model1.result.cores, *added.result.cores),
        (*model1.result.replays, *added.result.replays),
        (model1.raw_manifest.sha256, added.raw_manifest.sha256),
    )
    if (len(group.cores), len(group.replays)) != (630, 540):
        raise ValueError("collection_defense_schedule_mismatch")
    bases = sorted({c.identity.defense_base_id for c in group.cores})
    if len(bases) != DEFENSE_BASE_COUNT:
        raise ValueError("collection_defense_base_count")
    return (
        defense_comparison(group, "monitor-vs-enforce"),
        *(
            defense_comparison(
                group.select(tuple(c for c in group.cores if c.identity.defense_base_id == base)),
                "monitor-vs-enforce." + base[:16],
            )
            for base in bases
        ),
    )


def copy_public_stage(root: Path, source: str, writer: DatasetWriter, name: str) -> StageReference:
    """仅复制清单已登记的脱敏文件；不遍历原始请求目录。"""
    directory = inside(root, source)
    manifest = read_model(directory / "dataset-manifest.json", DatasetManifest)
    target = inside(writer.directory, "stages/" + name)
    target.mkdir(parents=True, exist_ok=False)
    for path in sorted({*manifest.files, "dataset-manifest.json", "sha256-manifest.json"}):
        src, dest = inside(directory, path), inside(target, path)
        guard_public(src.read_text(encoding="utf-8"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    return StageReference(
        directory="stages/" + name,
        original_dataset_directory=source,
        manifest=file_digest(directory / "dataset-manifest.json"),
        scheduled_core=manifest.scheduled_core,
        scheduled_replay=manifest.scheduled_replay,
    )


def export_collection(
    root: Path,
    paths: dict[str, str],
    output: Path,
    expected_directory: Path | None = None,
) -> CollectionManifest:
    """完整证据留在阶段子目录，顶层输出所有分层指标和比较。"""
    stages, reports = read_stages(root, paths)
    left, right = stages["f"], stages["g"]
    contract = validate_model_pair(
        (left.configuration, left.matrix, left.result.phase),
        (right.configuration, right.matrix, right.result.phase),
    )
    cross = model_reports(reports["f"], reports["g"])
    defenses = defense_reports(left, stages["h"])
    merged = DatasetReports(
        vectors=tuple(v for r in reports.values() for v in r.vectors),
        comparisons=(*tuple(c for r in reports.values() for c in r.comparisons), *cross, *defenses),
    )
    if any(not v.required_metrics_complete for v in merged.vectors) or any(
        not c.complete for c in merged.comparisons
    ):
        raise ValueError("collection_required_measurements_incomplete")
    if expected_directory is not None:
        verify_recomputed(expected_directory, merged, contract)
    writer = DatasetWriter(root, output)
    references = {name: copy_public_stage(root, paths[name], writer, name) for name in STAGES}
    writer.model("model-pair-contract.json", contract)
    write_reports(writer, "reports.json", merged)
    writer.csv("metrics-long.csv", metric_rows(merged), MetricCsvRow)
    writer.csv("condition-summary.csv", metric_rows(merged, "condition"), MetricCsvRow)
    writer.csv("skill-comparison-ready.csv", metric_rows(merged, "skill"), MetricCsvRow)
    for kind in ("model", "defense", "skill"):
        writer.csv(kind + "-comparison.csv", comparison_rows(merged, kind), ComparisonCsvRow)
    writer.text("README.md", readme())
    writer.schema_for(CollectionManifest)
    writer.schema_for(HashManifest)
    manifest = CollectionManifest(
        stages=references,
        model_pair_contract=contract,
        files=dict(writer.files),
        tables=dict(writer.tables),
    )
    writer.model("dataset-manifest.json", manifest)
    writer.model(
        "sha256-manifest.json",
        HashManifest(
            files={name: item.content for name, item in writer.files.items()},
        ),
    )
    return manifest


def verify_recomputed(
    directory: Path,
    reports: DatasetReports,
    contract: ModelPairContract,
) -> None:
    """重算时同时核对原发布 JSON 和全部 CSV 分卷，不仅读取新的计算结果。"""
    manifest = read_model(directory / "dataset-manifest.json", CollectionManifest)
    verify_files(directory, {name: item.content for name, item in manifest.files.items()})
    if (
        manifest.model_pair_contract != contract
        or read_reports(directory, "reports.json") != reports
    ):
        raise ValueError("collection_recomputed_comparison_drift")
    for filename, kind in (
        ("metrics-long.csv", None),
        ("condition-summary.csv", "condition"),
        ("skill-comparison-ready.csv", "skill"),
    ):
        validate_csv_rows(directory, manifest.tables[filename], metric_rows(reports, kind))
    for kind in ("model", "defense", "skill"):
        validate_csv_rows(
            directory,
            manifest.tables[kind + "-comparison.csv"],
            comparison_rows(reports, kind),
        )


def readme() -> str:
    """分层及重算入口以普通中文说明，完整事实不可省略为百分比。"""
    return (
        "# T17 第二版完整分层数据\n\n"
        "本集合包含 E、F、G 预检、G 正式和 H 新增部分。各自完整的任务、重放、回执、"
        "来源、用量、格式及原始记录清单在 `stages/e`、`stages/f`、`stages/g_canary`、"
        "`stages/g`、`stages/h`。阶段清单登记所有数据分卷，不能仅读首卷。\n\n"
        "顶层长表保留分子、分母、证据、区间和状态；模型分别报告，不跨模型、预检或协议"
        "计算总体比例。模型比较为 F 与 G；防御比较复用 F 加 H，共 630 个任务和 540 组重放。"
        "H 子目录只有新增的 270/270，不重复保存 F 样本。\n\n"
        "`model-pair-contract.json` 保留两侧原配置及阶段身份，列出接口、推理档位和批准修订"
        "的解释限制。比较描述模型及服务配置组合，不声称仅识别模型权重效应。"
        "同点值不证明统计等价，跨零区间记不确定。\n\n"
        "重算：从项目根目录运行 `.venv-skillflow/Scripts/python.exe "
        "scripts/t17_delivery/t17_collection.py --from-collection datasets/t17-v2 "
        "--output runs/t17-v2-recomputed-01`。仅读取公开事实，无需密钥或私有正文。"
        "阶段单独重算仍使用 `skillflow t17 v2 report --dataset <阶段目录> --output <新目录>`。"
        "技能比较使用 `skillflow compare-skills` 指向阶段目录；尚未开展不同攻击技能的实证排名。\n\n"
        "费用按冻结费率估算，不是账单；已撤回及失败尝试费用不计入实验分母，另见总费用表。"
        "独立审查状态为 REVIEW_UNAVAILABLE；本数据集合不单独宣告项目质量验收通过。\n"
    )


def main() -> None:
    """首次导出提供五个路径；重算从集合内的逐阶段事实加载。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", required=True)
    parser.add_argument("--from-collection")
    for name in STAGES:
        parser.add_argument("--" + name.replace("_", "-"))
    args = parser.parse_args()
    root = args.root.resolve()
    if args.from_collection:
        directory = inside(root, args.from_collection)
        manifest = read_model(directory / "dataset-manifest.json", CollectionManifest)
        paths = {
            name: inside(directory, item.directory).relative_to(root).as_posix()
            for name, item in manifest.stages.items()
        }
        for name, item in manifest.stages.items():
            if file_digest(inside(root, paths[name]) / "dataset-manifest.json") != item.manifest:
                raise ValueError("collection_child_manifest_changed")
    else:
        paths = {name: getattr(args, name) for name in STAGES}
        if not all(paths.values()):
            parser.error("provide all five stage datasets")
    result = export_collection(
        root,
        paths,
        inside(root, args.output),
        directory if args.from_collection else None,
    )
    print(f"collection_exported: stages={len(result.stages)}; new_api_calls=0", flush=True)  # noqa: T201


if __name__ == "__main__":
    main()
