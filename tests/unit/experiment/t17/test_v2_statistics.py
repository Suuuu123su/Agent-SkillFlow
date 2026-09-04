"""簇重抽样与描述性区间的独立公式对照，不把重复当独立样本。"""

import os
import random
import subprocess
import sys
from collections import defaultdict

import pytest

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.v2.measurements import contrast_interval, measure
from skillflow.experiment.t17.v2.statistics import cluster_contrast, wilson_interval
from skillflow.experiment.t17.v2.statistics_models import ClusterTerm, StatisticalInterval


def test_single_cluster_is_design_not_applicable() -> None:
    result = cluster_contrast(
        (ClusterTerm(cluster="s1", term="x", numerator=1, denominator=3),), {"x": 1}
    )
    assert result.status is MeasurementStatus.NOT_APPLICABLE
    assert result.complete_clusters == 1
    assert result.lower is None


def test_exact_bootstrap_matches_independent_resampling() -> None:
    samples = (0, 1, 0, 1, 1)
    rows = tuple(
        ClusterTerm(cluster=f"s{i}", term="x", numerator=3 * x, denominator=3)
        for i, x in enumerate(samples)
    )
    actual = cluster_contrast(rows, {"x": 1})
    generator = random.Random(17017)  # noqa: S311 -- 独立统计公式复验，不生成秘密。
    resampled = sorted(sum(generator.choices(samples, k=5)) / 5 for _ in range(10000))
    lower = resampled[249] + 0.975 * (resampled[250] - resampled[249])
    upper = resampled[9749] + 0.025 * (resampled[9750] - resampled[9749])
    assert actual.point == pytest.approx(0.6)
    assert actual.lower == pytest.approx(lower)
    assert actual.upper == pytest.approx(upper)
    assert actual.complete_clusters == 5
    assert actual.resamples == 10000
    assert actual.seed == 17017
    assert actual == cluster_contrast(rows, {"x": 1})


def test_repeats_stay_inside_the_same_five_clusters() -> None:
    repeated = tuple(
        ClusterTerm(cluster=f"s{i}", term="x", numerator=int(i % 2), denominator=1)
        for i in range(5)
        for _ in range(3)
    )
    combined = defaultdict(lambda: [0, 0])
    for row in repeated:
        combined[row.cluster][0] += row.numerator
        combined[row.cluster][1] += row.denominator
    collapsed = tuple(
        ClusterTerm(cluster=key, term="x", numerator=n, denominator=d)
        for key, (n, d) in combined.items()
    )
    assert cluster_contrast(repeated, {"x": 1}) == cluster_contrast(collapsed, {"x": 1})


def test_missing_contrast_cell_is_not_fabricated_as_zero() -> None:
    rows = (
        ClusterTerm(cluster="s1", term="left", numerator=1, denominator=1),
        ClusterTerm(cluster="s2", term="left", numerator=0, denominator=1),
    )
    result = cluster_contrast(rows, {"left": 1, "right": -1})
    assert result.status is MeasurementStatus.NOT_APPLICABLE
    assert result.complete_clusters == 0


def test_percentile_interval_is_not_artificially_widened_to_point() -> None:
    value = StatisticalInterval(
        status=MeasurementStatus.MEASURED,
        method="cluster_bootstrap",
        point=1,
        lower=2,
        upper=3,
        complete_clusters=5,
        resamples=10000,
        seed=17017,
    )
    assert value.lower == 2


def test_wilson_zero_success_has_positive_upper_and_empty_is_na() -> None:
    interval = wilson_interval(0, 15)
    assert interval.status is MeasurementStatus.MEASURED
    assert interval.lower == pytest.approx(0)
    assert 0.20 < interval.upper < 0.21
    assert wilson_interval(0, 0).status is MeasurementStatus.NOT_APPLICABLE


def test_contrast_keeps_sufficient_statistics_for_paired_comparisons() -> None:
    rows = (ClusterTerm(cluster="template-1", term="x", numerator=2, denominator=3),)
    value = contrast_interval(measure(2, 3, ("trial-1",)), rows, {"x": 1})
    assert value.cluster_terms == rows
    assert value.contrast_signs == {"x": 1}


def test_canonical_hash_does_not_depend_on_process_hash_seed() -> None:
    program = (
        "from skillflow.experiment.t17.v2.configuration import canonical_digest; "
        "print(canonical_digest(frozenset("
        "{'artifact-a','asset-b','skill-c','memory-d','tool-e'})))"
    )
    results = tuple(
        subprocess.run(
            [sys.executable, "-B", "-c", program],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "PYTHONHASHSEED": str(seed)},
        ).stdout
        for seed in (1, 2)
    )
    assert results[0] == results[1]
