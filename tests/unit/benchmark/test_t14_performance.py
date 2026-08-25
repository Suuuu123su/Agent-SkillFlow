from pathlib import Path

import pytest

from skillflow.benchmark.performance import (
    LocalPerformanceBaseline,
    PerformanceConfigurationError,
    PerformanceRequest,
    measure_local_performance,
)


def test_local_event_store_and_policy_baseline_is_measured(tmp_path: Path) -> None:
    baseline = measure_local_performance(PerformanceRequest(root=tmp_path, samples=8, warmup=2))

    assert baseline.environment.python
    assert baseline.environment.platform
    assert baseline.environment.processor
    assert baseline.environment.sqlite
    assert baseline.threshold_policy == "observational_baseline_only"
    assert set(baseline.measurements) == {
        "event_store_append",
        "event_store_get",
        "policy_engine_evaluate",
    }
    for measurement in baseline.measurements.values():
        assert measurement.samples == 8
        assert 0 <= measurement.minimum_us <= measurement.p50_us
        assert measurement.p50_us <= measurement.p95_us <= measurement.maximum_us
    with pytest.raises(PerformanceConfigurationError):
        measure_local_performance(PerformanceRequest(root=tmp_path, samples=1, warmup=0))


def test_recorded_performance_baseline_matches_contract() -> None:
    baseline = LocalPerformanceBaseline.model_validate_json(
        Path("docs/performance-baseline.json").read_text(encoding="utf-8")
    )

    assert baseline.threshold_policy == "observational_baseline_only"
    assert all(item.samples == 1_000 for item in baseline.measurements.values())


@pytest.mark.parametrize(("samples", "warmup"), [(0, 0), (1, -1)])
def test_performance_request_rejects_invalid_sample_counts(
    tmp_path: Path,
    samples: int,
    warmup: int,
) -> None:
    with pytest.raises(PerformanceConfigurationError):
        measure_local_performance(PerformanceRequest(root=tmp_path, samples=samples, warmup=warmup))
