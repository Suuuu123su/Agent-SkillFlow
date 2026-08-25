from skillflow.analysis.facts import ProvenanceSample
from skillflow.analysis.provenance_metrics import calculate_provenance
from skillflow.models.metrics import MetricStatus


def sample(
    artifact_id: str,
    depth: int,
    origins: tuple[set[str], set[str]],
) -> ProvenanceSample:
    observed, oracle = origins
    return ProvenanceSample(
        artifact_id=artifact_id,
        boundary_depth=depth,
        observed_origins=frozenset(observed),
        oracle_origins=frozenset(oracle),
        evidence_event_ids=(f"event-{artifact_id}",),
    )


def test_provenance_golden_partial_overlap_is_one_half() -> None:
    # Given: Oracle={A,B} 且 Observed={A,C}
    provenance = (sample("artifact-1", 0, ({"A", "C"}, {"A", "B"})),)

    # When: 计算来源指标
    result = calculate_provenance(provenance)

    # Then: TP=FP=FN=1 且三种比例均为 0.5
    assert result.overall.counts.model_dump() == {
        "tp": 1,
        "fp": 1,
        "fn": 1,
        "artifact_ids": ("artifact-1",),
    }
    assert result.overall.precision.value == 0.5
    assert result.overall.recall.value == 0.5
    assert result.overall.f1.value == 0.5


def test_provenance_all_missing_has_na_precision_and_zero_recall_f1() -> None:
    # Given: Oracle={A} 且 Observed 为空
    provenance = (sample("artifact-1", 0, (set(), {"A"})),)

    # When: 计算来源指标
    result = calculate_provenance(provenance).overall

    # Then: Precision=N/A，Recall=0，F1=0
    assert result.precision.status is MetricStatus.NOT_APPLICABLE
    assert result.precision.value is None
    assert result.recall.value == 0.0
    assert result.f1.value == 0.0


def test_provenance_empty_exposure_returns_structured_na() -> None:
    # Given: 没有任何来源暴露 Artifact
    # When: 计算空集合
    result = calculate_provenance(()).overall

    # Then: 三个比例均为结构化 N/A，而不是 0 或 NaN
    assert result.precision.status is MetricStatus.NOT_APPLICABLE
    assert result.recall.status is MetricStatus.NOT_APPLICABLE
    assert result.f1.status is MetricStatus.NOT_APPLICABLE
    assert result.precision.value is result.recall.value is result.f1.value is None


def test_provenance_multi_source_all_correct_and_duplicate_event_is_deduplicated() -> None:
    # Given: 同一 Artifact 的完整多来源记录被重复投影
    repeated = sample("artifact-1", 0, ({"A", "B"}, {"A", "B"}))

    # When: 计算两个相同结构化记录
    result = calculate_provenance((repeated, repeated)).overall

    # Then: 来源只按 Artifact 实例计算一次且全部正确
    assert result.counts.tp == 2
    assert result.precision.value == 1.0
    assert result.recall.value == 1.0
    assert result.f1.value == 1.0


def test_provenance_decay_uses_exact_adjacent_depth_recalls() -> None:
    # Given: 深度 0 Recall=1，深度 1 Recall=0.5
    provenance = (
        sample("artifact-0", 0, ({"A", "B"}, {"A", "B"})),
        sample("artifact-1", 1, ({"A"}, {"A", "B"})),
    )

    # When: 按边界深度计算 Decay
    result = calculate_provenance(provenance)

    # Then: 首层无前驱为 N/A，下一层衰减为 0.5
    assert result.by_boundary_depth[0].decay.status is MetricStatus.NOT_APPLICABLE
    assert result.by_boundary_depth[1].decay.numerator == 2
    assert result.by_boundary_depth[1].decay.denominator == 4
    assert result.by_boundary_depth[1].decay.value == 0.5
