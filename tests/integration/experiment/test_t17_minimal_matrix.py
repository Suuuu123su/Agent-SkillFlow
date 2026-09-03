import json
import socket
from pathlib import Path

import pytest

from skillflow.experiment.t17.minimal.artifacts import freeze_minimal_configuration
from skillflow.experiment.t17.minimal.runner import run_minimal_domain


@pytest.mark.parametrize("domain", ["scripted", "fake_reference"])
def test_minimal_matrix_runs_full_chain_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    domain: str,
) -> None:
    def deny_network(*args: object, **kwargs: object) -> None:
        pytest.fail("minimal offline matrix attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)
    configuration = freeze_minimal_configuration(Path(), tmp_path / "inputs")
    outcome = run_minimal_domain(configuration, tmp_path / domain, domain=domain)
    assert outcome.run_count == 23
    assert outcome.replay_count == 12
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (outcome.output_root / "runs").glob("*/minimal-run-record.json")
    ]
    assert len(records) == 23
    assert sum(item["task"]["task_success"] for item in records) == 20
    assert sum(item["task"]["safe_task_success"] for item in records) == 13
    assert all(item["actual_api_calls"] == 0 for item in records)
    assert all(item["runtime"]["task_success"] is None for item in records)
    assert all(
        hook["status"] in {"measured", "not_applicable"}
        for item in records
        for hook in item["hooks"]
    )
    standard = json.loads((outcome.output_root / "experiment-report.json").read_text())
    assert standard["raw_counts"]["unauthorized_executed_count"] == 8
    assert standard["ALR"]["value"] == 0.5
    assert standard["RIR_1"]["value"] == standard["RIR_3"]["value"] == 0.5
    assert (outcome.output_root / "phase-contract.json").exists()
    assert (outcome.output_root / "raw-manifest.json").exists()
    with pytest.raises((ValueError, OSError)):
        run_minimal_domain(configuration, tmp_path / domain, domain=domain)
