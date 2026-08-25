"""对一个已持久化 Run 执行预注册 Artifact 中和重放。"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Never

from pydantic import ValidationError

from skillflow.analysis.report_io import write_replay_risk_report
from skillflow.benchmark.replay import ReplayRunner, ReplayRunRequest
from skillflow.benchmark.replay_models import ReplayPairManifest
from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.experiment.errors import (
    CommandExitCode,
    ExperimentCommandError,
    ExperimentErrorCode,
)
from skillflow.experiment.io import replace_json_model, write_json_model
from skillflow.experiment.locations import locate_run
from skillflow.experiment.report_store import read_risk_report
from skillflow.models.execution import ExperimentManifest
from skillflow.models.reports import RunRiskReport
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document


@dataclass(frozen=True, slots=True)
class ReplayOutcome:
    """手动重放成功后的稳定身份。"""

    replay_id: str
    output_root: Path


def replay_persisted_run(
    run_id: str,
    artifact_id: str,
    runs_root: Path,
) -> ReplayOutcome:
    """按 RunResult 的 alias 绑定中和指定 Artifact。"""
    located = locate_run(runs_root, run_id)
    report = read_risk_report(located.run_root / "run-report.json")
    if not isinstance(report, RunRiskReport) or report.scenario is None:
        _invalid("run-report.json 缺少可重放身份")
    bindings = tuple(
        item for item in report.counterfactual_artifacts if item.artifact_id == artifact_id
    )
    if len(bindings) != 1:
        _invalid("neutralize-artifact 必须精确匹配一个预注册 alias")
    binding = bindings[0]
    scenario_path = Path(report.scenario.root)
    scenario = _configured_scenario(
        validate_yaml_document(scenario_path, Scenario),
        report,
    )
    namespace = f"manual-{hashlib.sha256(run_id.encode()).hexdigest()[:8]}"
    staging = located.experiment_root / "blobs" / "m" / namespace
    scripts, decisions = t12_fixture_registry()
    batch = ReplayRunner(scripts, decisions).run_configured(
        ReplayRunRequest(
            scenario_path=scenario_path,
            scenario=scenario,
            replay_root=staging,
            seed=f"{run_id}:{report.seed}:manual-replay",
            id_namespace=namespace,
            experiment_id=report.experiment_id or located.experiment_root.name,
            source_run_id=run_id,
            scenario_ref=report.scenario,
            redacted=report.redacted,
            target_alias=binding.alias,
        )
    )
    if len(batch.pairs) != 1:
        _invalid("预注册 alias 没有生成唯一 ReplayResult")
    pair = batch.pairs[0]
    destination = located.experiment_root / "replays" / pair.report.replay_id
    try:
        destination.mkdir(parents=False, exist_ok=False)
    except FileExistsError as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.OUTPUT_EXISTS,
            f"Replay 输出已存在：{pair.report.replay_id}",
            CommandExitCode.OUTPUT_CONFLICT,
        ) from error
    try:
        pair_manifest = ReplayPairManifest.model_validate_json(
            pair.manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.EXECUTION_FAILED,
            "内部 pair-manifest.json 缺失或无效",
            CommandExitCode.EXECUTION_FAILED,
        ) from error
    write_json_model(destination / "pair-manifest.json", pair_manifest)
    write_replay_risk_report(destination / "replay-report.json", pair.report)
    _register_replay(located.experiment_root, pair.report.replay_id)
    return ReplayOutcome(pair.report.replay_id, destination)


def _configured_scenario(scenario: Scenario, report: RunRiskReport) -> Scenario:
    harness_updates = {
        key: value
        for key, value in (
            ("shared_context", report.shared_context),
            ("persistent_memory", report.persistent_memory),
            ("auto_approve_tools", report.auto_approve_tools),
            ("provenance_mode", report.provenance_mode),
            ("implicit_text_authorization", report.implicit_text_authorization),
        )
        if value is not None
    }
    harness = scenario.harness.model_copy(update=harness_updates)
    execution = scenario.execution
    if report.enforcement_mode is not None:
        execution = execution.model_copy(update={"mode": report.enforcement_mode})
    return scenario.model_copy(update={"harness": harness, "execution": execution})


def _register_replay(root: Path, replay_id: str) -> None:
    path = root / "experiment-manifest.json"
    try:
        manifest = ExperimentManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.EXECUTION_FAILED,
            "experiment-manifest.json 缺失或无效",
            CommandExitCode.EXECUTION_FAILED,
        ) from error
    replay_ids = tuple(dict.fromkeys((*manifest.replay_ids, replay_id)))
    replace_json_model(path, manifest.model_copy(update={"replay_ids": replay_ids}))


def _invalid(detail: str) -> Never:
    raise ExperimentCommandError(
        ExperimentErrorCode.INPUT_VALUE_INVALID,
        detail,
        CommandExitCode.INPUT_INVALID,
    )
