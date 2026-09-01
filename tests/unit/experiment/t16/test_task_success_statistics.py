import math

from skillflow.experiment.t16.task_success_statistics import (
    ClusterRateCounts,
    PairedClusterCounts,
    bootstrap_hiaa_interval,
    bootstrap_paired_difference_interval,
    wilson_interval,
)


def test_wilson_interval_handles_boundary_rates_without_zero_width() -> None:
    zero = wilson_interval(0, 30)
    full = wilson_interval(30, 30)

    assert zero.lower == 0.0
    assert math.isclose(zero.upper, 0.11351339317396876)
    assert math.isclose(full.lower, 0.8864866068260311)
    assert full.upper == 1.0


def test_cluster_bootstrap_keeps_all_repeats_inside_semantic_instance() -> None:
    clusters = tuple(
        PairedClusterCounts(
            cluster_id=f"v{index:02d}",
            target_successes=3,
            target_total=3,
            control_successes=1,
            control_total=3,
        )
        for index in range(10)
    )

    estimate = bootstrap_paired_difference_interval(clusters, 10_000, 20260829)

    assert math.isclose(estimate.point_estimate, 2 / 3)
    assert math.isclose(estimate.interval.lower, 2 / 3)
    assert math.isclose(estimate.interval.upper, 2 / 3)
    assert estimate.cluster_count == 10


def test_hiaa_bootstrap_recomputes_four_pooled_cell_rates() -> None:
    clusters = tuple(
        ClusterRateCounts(
            cluster_id=f"v{index:02d}",
            successes=(0, 0, 1, 3),
            totals=(3, 3, 3, 3),
        )
        for index in range(10)
    )

    estimate = bootstrap_hiaa_interval(clusters, 10_000, 20260829)

    assert math.isclose(estimate.point_estimate, 2 / 3)
    assert estimate.interval.lower == estimate.interval.upper == estimate.point_estimate
