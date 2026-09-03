"""T17 指标闭环的根级子命令。"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Never

import typer
from pydantic import ValidationError

from skillflow.experiment.errors import ExperimentCommandError
from skillflow.experiment.t17.baseline_audit import (
    BaselineArtifactMissingError,
    build_baseline_audit,
    canonical_baseline_selections,
    write_baseline_audit,
)
from skillflow.experiment.t17.live_attempt_models import T17LivePreflightManifest
from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.live_preflight import T17LivePreflightError
from skillflow.experiment.t17.live_supervisor import (
    STAGE_MATRIX_FILENAMES,
    T17EmptyApiKeyError,
)
from skillflow.experiment.t17.live_supervisor_cli import run_live_supervisor_cli
from skillflow.experiment.t17.minimal.cli import minimal_app
from skillflow.experiment.t17.phase_integrity import T17PhaseIntegrityError
from skillflow.experiment.t17.phase_report import (
    T17PhaseReportRequest,
    write_phase_metrics_report,
)
from skillflow.experiment.t17.phase_report_loader import T17PhaseArtifactError
from skillflow.experiment.t17.scripted_golden import ScriptedGoldenMismatchError
from skillflow.experiment.t17.scripted_runner import (
    T17ScriptedRunRequest,
    execute_t17_scripted,
)
from skillflow.validation import DocumentValidationError

t17_app = typer.Typer(help="T17 指标、证据 Hook 与实验闭环。", no_args_is_help=True)
t17_app.add_typer(minimal_app, name="minimal")


def register_t17_commands(root: typer.Typer) -> None:
    """把 T17 子应用注册到 SkillFlow 根 CLI。"""
    root.add_typer(t17_app, name="t17")


@t17_app.command("audit-baseline")
def audit_baseline_command(
    project_root: Annotated[
        Path,
        typer.Option(exists=True, file_okay=False, help="SkillFlow 项目根目录。"),
    ] = Path(),
    source_revision: Annotated[
        str,
        typer.Option(help="本次冻结对应的 Git revision。"),
    ] = "working-tree",
    output: Annotated[
        Path,
        typer.Option(help="不可覆盖的 T17-A JSON 输出。"),
    ] = Path("docs/evidence/t17-baseline-audit.json"),
) -> None:
    """冻结 T12-T16 canonical 文件的字节哈希与 Evidence Domain。"""
    root = project_root.resolve()
    try:
        audit = build_baseline_audit(
            root,
            source_revision,
            datetime.now(UTC),
            canonical_baseline_selections(root),
        )
        write_baseline_audit(output, audit)
    except (BaselineArtifactMissingError, ExperimentCommandError) as error:
        _audit_failure(error)
    typer.echo(f"[通过] T17-A artifacts={audit.artifact_count} 输出={output}")


@t17_app.command("run-scripted")
def run_scripted_command(
    output_root: Annotated[
        Path,
        typer.Option(help="必须尚不存在的 Scripted Experiment 根目录。"),
    ],
    summary_output: Annotated[
        Path,
        typer.Option(help="不可覆盖的 T17-D 汇总 JSON。"),
    ],
    matrix: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False),
    ] = Path("scenarios/matrix/mvp.yaml"),
    registry: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False),
    ] = Path("experiments/t17/scenario_measurements.yaml"),
    golden: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False),
    ] = Path("experiments/t17/scripted_golden.yaml"),
) -> None:
    """执行 24 core、18 Replay、5 次确定性并验证 Golden。"""
    try:
        result = execute_t17_scripted(
            T17ScriptedRunRequest(
                matrix_path=matrix,
                registry_path=registry,
                golden_path=golden,
                output_root=output_root,
                summary_output=summary_output,
            )
        )
    except (
        DocumentValidationError,
        ExperimentCommandError,
        ScriptedGoldenMismatchError,
    ) as error:
        _scripted_failure(error)
    typer.echo(
        f"[通过] T17-D Runs={result.summary.observed_core_runs} "
        f"Replays={result.summary.observed_replay_pairs} 输出={result.output_root}"
    )


@t17_app.command("run-live")
def run_live_command(
    campaign_root: Annotated[
        Path,
        typer.Option(help="必须尚不存在的 T17 Live Campaign 根目录。"),
    ],
    project_root: Annotated[
        Path,
        typer.Option(exists=True, file_okay=False, help="SkillFlow 项目根目录。"),
    ] = Path(),
    stage: Annotated[
        T17LiveStage,
        typer.Option(help="首个待执行的付费阶段。"),
    ] = T17LiveStage.CANARY,
    budget_proposal: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, help="零调用预算提案。"),
    ] = Path("docs/evidence/t17-e-budget-proposal.json"),
) -> None:
    """逐阶段确认费用，隐藏读取一次密钥并运行 Reference Harness。"""
    try:
        results = run_live_supervisor_cli(
            project_root,
            campaign_root,
            stage,
            budget_proposal,
        )
    except (
        T17EmptyApiKeyError,
        T17LivePreflightError,
        DocumentValidationError,
        ExperimentCommandError,
        ValidationError,
        OSError,
    ) as error:
        _live_failure(error)
    if (
        not results
        or not results[-1].result.summary.live_gate_passed
        or not results[-1].metrics.required_metrics_complete
    ):
        raise typer.Exit(code=2)
    typer.echo(f"[通过] T17 Live 已完成阶段数={len(results)}")


@t17_app.command("report")
def report_command(
    attempt_root: Annotated[
        Path,
        typer.Option(exists=True, file_okay=False, help="T17 Live Attempt 根目录。"),
    ],
    project_root: Annotated[
        Path,
        typer.Option(exists=True, file_okay=False, help="SkillFlow 项目根目录。"),
    ] = Path(),
    output: Annotated[
        Path | None,
        typer.Option(help="不可覆盖的 Phase 指标 JSON；默认写入 Attempt。"),
    ] = None,
) -> None:
    """复验 Raw SHA 并机械生成完整 T17 Phase 指标。"""
    root = project_root.resolve()
    attempt = attempt_root.resolve()
    try:
        preflight = T17LivePreflightManifest.model_validate_json(
            (attempt / "preflight.json").read_text(encoding="utf-8")
        )
        report = write_phase_metrics_report(
            T17PhaseReportRequest(
                attempt_root=attempt,
                matrix_path=(
                    root / "experiments" / "t17" / STAGE_MATRIX_FILENAMES[preflight.stage]
                ),
                registry_path=root / "experiments" / "t17" / "scenario_measurements.yaml",
                base_matrix_path=root / "scenarios" / "matrix" / "mvp.yaml",
                output_path=output or attempt / "phase-metrics.json",
            )
        )
    except (
        T17PhaseArtifactError,
        T17PhaseIntegrityError,
        ExperimentCommandError,
        ValidationError,
        OSError,
    ) as error:
        _report_failure(error)
    typer.echo(
        f"[通过] T17 report metrics_complete={report.required_metrics_complete} "
        f"输出={output or attempt / 'phase-metrics.json'}"
    )


def _audit_failure(error: BaselineArtifactMissingError | ExperimentCommandError) -> Never:
    typer.echo(f"[失败] {error}", err=True)
    raise typer.Exit(code=2) from error


def _scripted_failure(
    error: DocumentValidationError | ExperimentCommandError | ScriptedGoldenMismatchError,
) -> Never:
    typer.echo(f"[失败] {error}", err=True)
    raise typer.Exit(code=2) from error


def _live_failure(
    error: (
        T17EmptyApiKeyError
        | T17LivePreflightError
        | DocumentValidationError
        | ExperimentCommandError
        | ValidationError
        | OSError
    ),
) -> Never:
    typer.echo(f"[失败] {error.__class__.__name__}: {error}", err=True)
    raise typer.Exit(code=2) from error


def _report_failure(
    error: (
        T17PhaseArtifactError
        | T17PhaseIntegrityError
        | ExperimentCommandError
        | ValidationError
        | OSError
    ),
) -> Never:
    typer.echo(f"[失败] {error.__class__.__name__}: {error}", err=True)
    raise typer.Exit(code=2) from error
