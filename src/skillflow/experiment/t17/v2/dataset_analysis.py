"""标准数据集报告编排：阶段、条件、技能、跨模型、防御各自分层。"""

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.comparisons import defense_comparison, model_comparison
from skillflow.experiment.t17.v2.dataset_models import DatasetReports
from skillflow.experiment.t17.v2.loaded_models import LoadedStage
from skillflow.experiment.t17.v2.report_models import ComparisonReport, MetricVectorReport
from skillflow.experiment.t17.v2.reporting import build_vector, condition_vectors
from skillflow.experiment.t17.v2.skill_comparison import skill_vectors_and_pairs


def dataset_reports(stages: tuple[LoadedStage, ...]) -> DatasetReports:
    """只分析实际提供阶段；缺少第二模型时不制造零值比较。"""
    vectors: list[MetricVectorReport] = []
    comparisons: list[ComparisonReport] = []
    index: dict[T17LiveStage, LoadedStage] = {}
    for stage in stages:
        phase = stage.result.phase
        if phase.stage in index:
            raise ValueError("v2_dataset_duplicate_stage_or_attempt")
        index[phase.stage] = stage
        group = stage.group()
        prefix = phase.domain + "." + phase.stage.value
        vectors.append(build_vector(group, prefix))
        vectors.extend(condition_vectors(group, prefix))
        vectors.extend(
            build_vector(
                group.select(tuple(c for c in group.cores if c.identity.enforcement_mode == mode)),
                prefix + "." + mode.value,
                "mode",
            )
            for mode in sorted({c.identity.enforcement_mode for c in group.cores})
        )
        skill_vectors, skill_pairs = skill_vectors_and_pairs(group, prefix)
        vectors.extend(skill_vectors)
        comparisons.extend(skill_pairs)
    if T17LiveStage.MODEL1 in index and T17LiveStage.MODEL2 in index:
        left, right = index[T17LiveStage.MODEL1].group(), index[T17LiveStage.MODEL2].group()
        comparisons.append(model_comparison(left, right, "model1-vs-model2"))
        for condition in sorted({c.identity.condition_id for c in left.cores}):
            lside = left.select(
                tuple(c for c in left.cores if c.identity.condition_id == condition)
            )
            rside = right.select(
                tuple(c for c in right.cores if c.identity.condition_id == condition)
            )
            comparisons.append(model_comparison(lside, rside, "model1-vs-model2." + condition))
    if T17LiveStage.MODEL1 in index and T17LiveStage.DEFENSE in index:
        comparisons.extend(_defense(index[T17LiveStage.MODEL1], index[T17LiveStage.DEFENSE]))
    return DatasetReports(vectors=tuple(vectors), comparisons=tuple(comparisons))


def _defense(model1: LoadedStage, added: LoadedStage) -> tuple[ComparisonReport, ...]:
    if model1.configuration != added.configuration:
        raise ValueError("v2_defense_configuration_drift")
    group = AnalysisGroup(
        model1.configuration,
        (*model1.result.cores, *added.result.cores),
        (*model1.result.replays, *added.result.replays),
        (model1.raw_manifest.sha256, added.raw_manifest.sha256),
    )
    result = [defense_comparison(group, "monitor-vs-enforce")]
    for base in sorted({c.identity.defense_base_id for c in group.cores}):
        selected = group.select(tuple(c for c in group.cores if c.identity.defense_base_id == base))
        result.append(defense_comparison(selected, "monitor-vs-enforce." + base[:16]))
    return tuple(result)
