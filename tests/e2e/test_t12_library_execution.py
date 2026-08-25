import json
from pathlib import Path

import pytest

from skillflow.benchmark.runner import ScenarioRunner
from skillflow.benchmark.t12_fixtures import t12_fixture_registry

SCENARIO_PATHS = tuple(
    sorted(
        (
            *Path("scenarios/benign").glob("*.yaml"),
            *Path("scenarios/attacks").glob("*.yaml"),
        )
    )
)
DETERMINISM_REPEATS = 5


@pytest.mark.parametrize("scenario_path", SCENARIO_PATHS, ids=lambda path: path.stem)
def test_full_t12_library_runs_safely_and_deterministically(
    scenario_path: Path,
    tmp_path: Path,
) -> None:
    scripts, decisions = t12_fixture_registry()
    runner = ScenarioRunner(scripts, decisions)
    fingerprints: list[tuple[bytes, ...]] = []

    for repeat in range(DETERMINISM_REPEATS):
        run_root = tmp_path / f"repeat-{repeat}"
        result = runner.run(scenario_path, run_root, seed=f"t12-{scenario_path.stem}")
        report = json.loads(result.risk_report_path.read_text(encoding="utf-8"))

        assert report["task_success"] is True
        assert result.shell_records == ()
        assert all(record.sink.root.startswith("mock://") for record in result.network_records)
        assert result.workspace_root.parent == run_root
        fingerprints.append(
            (
                result.observed_trace_path.read_bytes(),
                result.oracle_trace_path.read_bytes(),
                result.security_graph_path.read_bytes(),
                result.risk_report_path.read_bytes(),
            )
        )

    assert all(fingerprint == fingerprints[0] for fingerprint in fingerprints[1:])
