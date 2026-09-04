"""第二版单任务执行和本地检查点；模型不参与任何真值或身份生成。"""

import hashlib
import time
from dataclasses import dataclass, replace
from pathlib import Path

from pydantic import ConfigDict

from skillflow.adapters.checkpoint import HarnessCheckpoint, verify_harness_checkpoint
from skillflow.benchmark.runner import ScenarioRunLayout, ScenarioRunner, ScenarioRunRequest
from skillflow.experiment.inputs import apply_variant, namespace_grants
from skillflow.experiment.matrix_support import build_run_metadata
from skillflow.experiment.run_artifacts import require_mock_only
from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.reference_backend import ReferenceModelClient
from skillflow.experiment.t17.v2.catalog_models import SkillBundle
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix, V2Trial
from skillflow.experiment.t17.v2.frozen import FrozenFile, digest_files, inside
from skillflow.experiment.t17.v2.portable import capture_core
from skillflow.experiment.t17.v2.run_models import CoreTerminal, PhaseContract
from skillflow.experiment.t17.v2.runtime import V2HarnessFactory
from skillflow.experiment.t17.v2.runtime_models import RunCapture
from skillflow.experiment.t17.v2.stage_contract import unit_identity
from skillflow.models.base import StrictModel
from skillflow.models.references import FixtureImplementationRef
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document


class PrivateCheckpoint(StrictModel):
    """仅存本地的完整检查点；公开清单只登记其哈希。"""

    model_config = ConfigDict(
        extra="forbid", frozen=True, ser_json_bytes="base64", val_json_bytes="base64"
    )
    checkpoint: HarnessCheckpoint


PrivateCheckpoint.model_rebuild(
    _types_namespace={"FixtureImplementationRef": FixtureImplementationRef}
)


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """一个尝试的固定依赖，绝不含密钥值。"""

    project_root: Path
    output: Path
    configuration: V2Configuration
    matrix: V2Matrix
    phase: PhaseContract
    client: ReferenceModelClient | None


@dataclass(frozen=True, slots=True)
class CoreExecution:
    """可公开终态和只保留到相关回放结束的私有保存点。"""

    terminal: CoreTerminal
    scenario: Scenario
    scenario_path: Path
    bundle: SkillBundle
    capture: RunCapture
    seed: str


def compact_id(identifier: str) -> str:
    """短目录名避免 Windows 长路径，完整身份仍保存在记录中。"""
    return hashlib.sha256(identifier.encode()).hexdigest()[:24]


def file_inventory(root: Path, directory: Path) -> dict[str, FrozenFile]:
    """数据库关闭后登记该单元所有实际文件。"""
    if not directory.exists():
        return {}
    paths = tuple(
        sorted(p.relative_to(root).as_posix() for p in directory.rglob("*") if p.is_file())
    )
    return digest_files(root, paths)


def execute_core(context: ExecutionContext, trial: V2Trial) -> CoreExecution:
    """每条任务隔离数据库和接收端，回放点来自本次真实执行。"""
    started = time.perf_counter_ns()
    entry = next(
        e
        for e in context.configuration.catalog.variants
        if e.skill_variant_id == trial.skill_variant_id
    )
    bundle = SkillBundle.model_validate_json(
        inside(context.project_root, entry.source_path).read_text(encoding="utf-8")
    )
    scenario_path = inside(context.project_root, entry.scenario_path)
    run_id = "run-" + compact_id(trial.trial_id)
    scenario = namespace_grants(
        apply_variant(validate_yaml_document(scenario_path, Scenario), trial.configuration), run_id
    )
    factory = V2HarnessFactory(context.client, trial.task_prompt)
    runner = ScenarioRunner(
        bundle.scripts, bundle.decisions, factory, execution_policy=factory.execution_policy
    )
    directory = context.output / "core" / compact_id(trial.trial_id)
    directory.parent.mkdir(parents=True, exist_ok=True)
    # 模型与防御的配对使用相同随机种子；数据库按任务隔离，ID 由 Run 绑定。
    seed = (
        f"{trial.defense_base_id}:{trial.semantic_template_id}:"
        f"{trial.repeat_index}:{trial.configuration.seed}"
    )
    metadata = replace(
        build_run_metadata(
            context.output.name,
            trial.configuration,
            trial.configuration.harm_selector,
            redacted=True,
        ),
        backend="reference_harness",
    )
    result = runner.run_configured(
        ScenarioRunRequest(
            scenario_path,
            scenario,
            run_id,
            seed,
            ScenarioRunLayout(
                directory,
                directory,
                directory / "state.sqlite",
                directory / "workspace",
                directory / "graph.json",
                directory / "legacy-run-report.json",
            ),
            metadata,
        )
    )
    require_mock_only(result)
    task = next(t for t in context.configuration.tasks if t.scenario_path == entry.scenario_path)
    data = capture_core(
        result,
        scenario,
        task,
        metadata,
        context.configuration.claim_bindings[entry.skill_variant_id],
    )
    capture = factory.captures[run_id]
    for alias, source in capture.checkpoints.items():
        checkpoint = PrivateCheckpoint(checkpoint=source.checkpoint)
        checkpoint_path = directory / ("checkpoint-" + compact_id(alias) + ".json")
        write_checked_json(checkpoint_path, checkpoint)
        restored = PrivateCheckpoint.model_validate_json(
            checkpoint_path.read_text(encoding="utf-8")
        )
        verify_harness_checkpoint(restored.checkpoint)
    write_checked_json(directory / "portable-core.json", data)
    terminal = CoreTerminal(
        identity=unit_identity(context.phase, context.matrix, trial, trial.trial_id),
        status="completed",
        run_id=run_id,
        data=data,
        decisions=tuple(capture.decisions),
        issues=tuple(capture.issues),
        wall_latency_ms=(time.perf_counter_ns() - started) / 1_000_000,
        raw_files=file_inventory(context.output, directory),
    )
    return CoreExecution(terminal, scenario, scenario_path, bundle, capture, seed)
