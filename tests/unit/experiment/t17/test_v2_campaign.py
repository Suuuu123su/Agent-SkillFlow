"""监督入口先验预算和证据；无批准不能申请密钥或发请求。"""

import getpass
import warnings
from pathlib import Path

import pytest
from tests.unit.experiment.t17.v2_test_history import write_history
from typer.testing import CliRunner

from skillflow.cli import app
from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.campaign import read_campaign_key
from skillflow.experiment.t17.v2.campaign_models import CredentialInputError
from skillflow.experiment.t17.v2.configuration import build_configuration, write_configuration
from skillflow.experiment.t17.v2.cost_history import historical_usage
from skillflow.experiment.t17.v2.cost_plan import graph_call_counts
from skillflow.experiment.t17.v2.matrix import build_matrix


def test_key_read_once_and_echo_fallback_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def reader(prompt: str) -> str:
        calls.append(prompt)
        return "test-secret-never-written"

    monkeypatch.setattr(getpass, "getpass", reader)
    assert read_campaign_key().get_secret_value() == "test-secret-never-written"
    assert len(calls) == 1

    def echo_reader(prompt: str) -> str:
        warnings.warn("echo unavailable", getpass.GetPassWarning, stacklevel=1)
        pytest.fail("不允许回显后再读密钥")

    monkeypatch.setattr(getpass, "getpass", echo_reader)
    with pytest.raises(CredentialInputError):
        read_campaign_key()


def test_live_command_rejects_missing_approval_before_secret(
    t17_cli_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(prompt: str) -> str:
        pytest.fail("预算批准前请求了密钥")

    monkeypatch.setattr(getpass, "getpass", forbidden)
    result = CliRunner().invoke(
        app,
        [
            "t17",
            "v2",
            "run-live",
            "--protocol",
            str(t17_cli_root),
            "--cost-plan",
            str(t17_cli_root / "missing-plan.json"),
            "--approval",
            str(t17_cli_root / "missing-approval.json"),
            "--output",
            str(t17_cli_root / "never-started"),
        ],
    )
    assert result.exit_code == 2
    assert "No such command" not in result.output
    assert not (t17_cli_root / "never-started").exists()


def test_cost_projection_uses_graph_and_differenced_history(t17_cli_root: Path) -> None:
    root = Path.cwd()
    config, bundles = build_configuration(root, t17_cli_root / "cost-config")
    write_configuration(root, t17_cli_root / "cost-config", config, bundles)
    matrix = build_matrix(root, config, T17LiveStage.CANARY)
    counts = graph_call_counts(root, matrix)
    assert len(counts) == 42
    assert all(0 <= count <= 16 for count in counts)
    assert sum(counts) > 24
    path = t17_cli_root / "synthetic-history.jsonl"
    write_history(path)
    history, samples = historical_usage(root, path)
    assert history.observed_responses == len(samples) == 2
    assert history.observed_input_tokens == sum(s.input_tokens for s in samples) == 30
    assert history.new_prompt_allowance_tokens == 1024
