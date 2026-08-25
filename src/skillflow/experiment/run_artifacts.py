"""Run 派生产物清单与 Mock-only 安全边界。"""

from dataclasses import dataclass

from skillflow.benchmark.runner import ScenarioRunResult
from skillflow.experiment.errors import (
    CommandExitCode,
    ExperimentCommandError,
    ExperimentErrorCode,
)
from skillflow.experiment.io import sha256_file, write_json_model
from skillflow.experiment.layout import ExperimentLayout
from skillflow.models.execution import ArtifactDigest, ExecutionBackend, RunManifest
from skillflow.models.references import ScenarioPath


@dataclass(frozen=True, slots=True)
class RunArtifactRequest:
    """写 RunManifest 所需的稳定参数。"""

    layout: ExperimentLayout
    scenario: ScenarioPath
    result: ScenarioRunResult
    redacted: bool


def write_run_manifest(request: RunArtifactRequest) -> RunManifest:
    """写入只含相对身份与派生产物摘要的 RunManifest。"""
    report = request.result.risk_report
    paths = (
        request.result.observed_trace_path,
        request.result.oracle_trace_path,
        request.result.security_graph_path,
        request.result.risk_report_path,
    )
    manifest = RunManifest(
        run_id=request.result.run_id,
        experiment_id=report.experiment_id or request.layout.root.name,
        scenario=request.scenario,
        scenario_id=request.result.scenario_id,
        variant=report.variant or "single",
        seed=report.seed if report.seed is not None else 0,
        backend=ExecutionBackend.SCRIPTED,
        run_role=report.run_role,
        redacted=request.redacted,
        task_success=report.task_success is True,
        harm=report.harm is True,
        artifacts=tuple(ArtifactDigest(name=path.name, sha256=sha256_file(path)) for path in paths),
    )
    write_json_model(request.result.risk_report_path.parent / "run-manifest.json", manifest)
    return manifest


def require_mock_only(result: ScenarioRunResult) -> None:
    """拒绝 Shell 记录或任何非 mock 网络目标。"""
    if result.shell_records or any(
        not record.sink.root.startswith("mock://") for record in result.network_records
    ):
        raise ExperimentCommandError(
            ExperimentErrorCode.EXECUTION_FAILED,
            "T13 只允许 Mock 网络且禁止 Shell 记录",
            CommandExitCode.EXECUTION_FAILED,
        )
