"""启动失败、记账失败和人工中断都必须保存完整的调度终态。"""

from pathlib import Path

import pytest

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.reference_backend import ReferenceModelDecision, ReferenceModelRequest
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix
from skillflow.experiment.t17.v2.configuration import build_configuration, write_configuration
from skillflow.experiment.t17.v2.dataset_writing import guard_public
from skillflow.experiment.t17.v2.matrix import build_matrix
from skillflow.experiment.t17.v2.run_models import PhaseContract, UnitUsage
from skillflow.experiment.t17.v2.stage import StageSetup, run_stage


class FailingClient:
    def __init__(self, location: str) -> None:
        self.location = location
        self.calls = 0

    def authorized_for(self, matrix_sha256: str) -> bool:
        return True

    def open_phase(self, output: Path, phase: PhaseContract) -> None:
        if self.location == "startup":
            raise OSError("simulated_startup_failure")

    def begin_unit(self, unit_id: str) -> None:
        pass

    def unit_usage(self) -> UnitUsage:
        if self.location == "usage":
            raise OSError("simulated_accounting_failure")
        if self.location == "partial":
            return UnitUsage(complete=False, missing_reason="unclosed_attempt")
        return UnitUsage()

    def decide(self, request: ReferenceModelRequest) -> ReferenceModelDecision:
        self.calls += 1
        if self.location == "interrupt":
            raise KeyboardInterrupt
        if self.location == "partial":
            return ReferenceModelDecision(
                selected_action_ids=request.allowed_action_ids,
                output_text=request.expected_output_text,
            )
        raise OSError("simulated_provider_failure")


@pytest.fixture(scope="module")
def inputs(t17_cli_root: Path) -> tuple[V2Configuration, V2Matrix]:
    output = t17_cli_root / "failure-inputs"
    config, bundles = build_configuration(Path.cwd(), output)
    write_configuration(Path.cwd(), output, config, bundles)
    return config, build_matrix(Path.cwd(), config, T17LiveStage.CANARY)


@pytest.mark.parametrize("location", ["startup", "usage", "interrupt", "partial"])
def test_framework_failure_keeps_every_scheduled_terminal(
    t17_cli_root: Path, inputs: tuple[V2Configuration, V2Matrix], location: str
) -> None:
    config, matrix = inputs
    client = FailingClient(location)
    try:
        result = run_stage(
            StageSetup(
                Path.cwd(), t17_cli_root / location, config, matrix, "fake_reference", client
            )
        )
    except KeyboardInterrupt:
        pytest.fail("人工中断未保存预定任务终态")
    assert len(result.cores) == 24
    assert len(result.replays) == 18
    assert not result.gate.passed
    assert result.cores[0].status == "infrastructure_invalid"
    assert all(c.status == "not_run" for c in result.cores[1:])
    assert client.calls == (
        len(result.cores[0].decisions)
        if location == "partial"
        else (0 if location == "startup" else 1)
    )
    assert (t17_cli_root / location / "raw-manifest.json").is_file()
    if location == "usage":
        assert not result.cores[0].usage.complete


@pytest.mark.parametrize("value", ["C:/Users/private", r"E:\secret", "sk-" + "x" * 32])
def test_public_data_rejects_credentials_and_host_paths(value: str) -> None:
    with pytest.raises(ValueError, match="v2_public_"):
        guard_public(value)
