"""同模型、同防御和相同环境下比较具体技能文件；家族标签只作分组。"""

from collections import defaultdict

from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.comparisons import compare_vectors
from skillflow.experiment.t17.v2.configuration import canonical_digest
from skillflow.experiment.t17.v2.report_models import ComparisonReport, MetricVectorReport
from skillflow.experiment.t17.v2.reporting import build_vector
from skillflow.experiment.t17.v2.run_models import CoreTerminal

_CONTENT_AXES = {"variant", "scenario", "target_skill_present", "hiaa_cell"}


def skill_vectors_and_pairs(
    group: AnalysisGroup, prefix: str
) -> tuple[tuple[MetricVectorReport, ...], tuple[ComparisonReport, ...]]:
    """内容版本与能力匹配已经冻结；不同环境不自动池化。"""
    grouped: dict[tuple[str, str], list[CoreTerminal]] = defaultdict(list)
    for core in group.cores:
        environment = canonical_digest(
            group.variant(core).model_dump(mode="json", exclude=_CONTENT_AXES)
        )
        grouped[(core.identity.skill_variant_id, environment)].append(core)
    reports = {
        key: build_vector(
            group.select(tuple(cores)), prefix + ".skill." + key[0] + "." + key[1][:12], "skill"
        )
        for key, cores in sorted(grouped.items())
    }
    comparisons = []
    for entry in group.configuration.catalog.variants:
        neutral = entry.neutral_pair_skill_id
        if neutral is None:
            continue
        for (skill, environment), left in reports.items():
            right = reports.get((neutral, environment))
            if skill != entry.skill_variant_id or right is None:
                continue
            _check_pair_clusters(grouped[(skill, environment)], grouped[(neutral, environment)])
            comparisons.append(
                compare_vectors(
                    left, right, prefix + ".skill-pair." + skill + "." + environment[:12], "skill"
                )
            )
    return tuple(reports.values()), tuple(comparisons)


def _check_pair_clusters(left: list[CoreTerminal], right: list[CoreTerminal]) -> None:
    def key(core: CoreTerminal) -> tuple[str, int]:
        return core.identity.semantic_template_id, core.identity.repeat_index

    left_ids, right_ids = tuple(map(key, left)), tuple(map(key, right))
    if (
        len(set(left_ids)) != len(left_ids)
        or len(set(right_ids)) != len(right_ids)
        or set(left_ids) != set(right_ids)
    ):
        raise ValueError("v2_skill_comparison_cluster_pair_mismatch")
