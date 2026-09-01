import ast
import json
import socket
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from skillflow.experiment.t16.dry_run import DryRunRequest, execute_t16b
from skillflow.experiment.t16.dry_run_checks import (
    NetworkProbe,
    UnexpectedNetworkAccessError,
    verify_network_probe_is_blocked,
)
from skillflow.experiment.t16.dry_run_io import read_trial_records

NetworkArgument = str | int | float | tuple[str, int] | None


def forbid_network(*_args: NetworkArgument, **_kwargs: NetworkArgument) -> None:
    raise UnexpectedNetworkAccessError


class AccidentalNetworkProbe:
    def attempt(self) -> None:
        socket.create_connection(("example.invalid", 443))


def test_full_t16b_run_writes_720_simulation_only_records_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: 所有底层 socket 创建入口均被硬失败替换。
    monkeypatch.setattr(socket, "create_connection", forbid_network)
    monkeypatch.setattr(socket, "socket", forbid_network)
    output = tmp_path / "t16b-run"
    evidence = tmp_path / "evidence"

    # When: 执行与未来真实实验相同的调度、记账、保存和报告链路。
    summary = execute_t16b(
        DryRunRequest(
            project_root=Path.cwd(),
            output_root=output,
            evidence_root=evidence,
        )
    )

    # Then: 结果严格标记模拟，且没有把 Fake 重复当独立统计样本。
    records = read_trial_records(output / "trial-results.jsonl")
    assert len(records) == 720
    assert summary.simulation_only is True
    assert summary.real_attack_success_rate_status.value == "not_applicable"
    assert summary.real_model_safety_conclusion_supported is False
    assert summary.fake_repeats_are_independent_samples is False
    assert summary.matrix_integrity.scheduled_trial_count == 720
    assert {path.name for path in evidence.iterdir()} == {
        "t16b-cost-simulation.json",
        "t16b-failure-injection.json",
        "t16b-fake-run-summary.json",
        "t16b-matrix-integrity.json",
    }
    schema = json.loads(
        Path("schemas/t16b-dry-run-summary.schema.json").read_text(encoding="utf-8")
    )
    payload = json.loads((evidence / "t16b-fake-run-summary.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)


def test_accidental_network_probe_is_caught_without_real_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: 一个测试专用、会误触网络原语的 Probe。
    monkeypatch.setattr(socket, "create_connection", forbid_network)
    probe: NetworkProbe = AccidentalNetworkProbe()

    # When / Then: 保护层捕获错误，真实连接没有发生。
    result = verify_network_probe_is_blocked(probe)
    assert result.kind.value == "unexpected_network"
    assert result.blocked is True


def test_t16b_runtime_has_no_network_or_environment_access_path() -> None:
    # Given: T16-B 的全部运行模块语法树。
    modules = Path("src/skillflow/experiment/t16").glob("dry_run*.py")
    trees = tuple(ast.parse(path.read_text(encoding="utf-8")) for path in modules)

    # When: 提取直接导入和敏感环境读取标记。
    imported = {
        alias.name.split(".", maxsplit=1)[0]
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module.split(".", maxsplit=1)[0]
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    source = "\n".join(ast.unparse(tree) for tree in trees).upper()

    # Then: 实现既没有网络库，也没有凭据/环境读取入口。
    assert imported.isdisjoint({"aiohttp", "http", "os", "requests", "socket", "urllib"})
    assert all(marker not in source for marker in ("API_KEY", "GETENV", "ENVIRON"))
