"""24 核心、18 成对重放和每核心五份确定性执行的固定脚本验收。"""

from pathlib import Path

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.canonical import canonical_digest, model_digest
from skillflow.experiment.t17.v2.golden_models import GoldenReport, TaskGolden, golden_specification
from skillflow.experiment.t17.v2.metrics import metric_vector
from skillflow.experiment.t17.v2.run_models import CoreTerminal
from skillflow.experiment.t17.v2.stage import StageSetup, run_stage
from skillflow.experiment.t17.v2.static_protocol import verify_protocol
from skillflow.experiment.t17.v2.unit_execution import (
    ExecutionContext,
    execute_core,
    file_inventory,
)


def run_golden(root: Path, protocol: Path, output: Path) -> GoldenReport:
    """只有第一份包含成对重放；另外四份只检验核心确定性，不混入统计分母。"""
    config, matrices = verify_protocol(root, protocol)
    matrix = next(m for m in matrices if m.stage is T17LiveStage.CANARY)
    spec = golden_specification()
    if {t.condition_id for t in matrix.trials} != set(spec.tasks):
        raise ValueError("v2_golden_requires_exact_registered_matrix")
    output.resolve().relative_to(root.resolve())
    output.mkdir(parents=True, exist_ok=False)
    write_checked_json(output / "expected.json", spec)
    reference = run_stage(StageSetup(root, output / "reference", config, matrix, "scripted", None))
    fingerprints = {c.identity.condition_id: [_fingerprint(c)] for c in reference.cores}
    for replica in range(2, spec.core_replicas + 1):
        context = ExecutionContext(
            root, output / f"replica-{replica}", config, matrix, reference.phase, None
        )
        for trial in matrix.trials:
            core = execute_core(context, trial).terminal
            fingerprints[trial.condition_id].append(_fingerprint(core))
    tasks = {
        c.identity.condition_id: TaskGolden(
            task_success=c.data.proof.task.task_success,
            safe_task_success=c.data.proof.task.safe_task_success,
        )
        for c in reference.cores
        if c.data is not None
    }
    vector = metric_vector(AnalysisGroup(config, reference.cores, reference.replays))
    metrics = {name: vector[name].value for name in spec.expected_metrics}
    failures = []
    if not reference.gate.passed:
        failures.append("full_phase_gate")
    if tasks != spec.tasks:
        failures.append("independent_task_expectations")
    if metrics != spec.expected_metrics:
        failures.append("independent_risk_expectations")
    if any(len(set(values)) != 1 for values in fingerprints.values()):
        failures.append("five_replica_determinism")
    neutral = {"c1-context-grid-p00", "c1-context-grid-p01"}
    if any(
        r.proof is None or r.proof.ci != 0
        for r in reference.replays
        if r.identity.condition_id in neutral
    ):
        failures.append("neutral_control_causal_zero")
    report = GoldenReport(
        configuration_sha256=model_digest(config),
        phase_contract_sha256=model_digest(reference.phase),
        expected_sha256=model_digest(spec),
        passed=not failures,
        core=len(reference.cores),
        replay=len(reference.replays),
        replicas=spec.core_replicas,
        fingerprints={k: tuple(v) for k, v in fingerprints.items()},
        tasks=tasks,
        metrics=metrics,
        failures=tuple(failures),
        raw_files={p: f.sha256 for p, f in file_inventory(output, output).items()},
    )
    write_checked_json(output / "golden-report.json", report)
    return report


def _fingerprint(core: CoreTerminal) -> str:
    if core.data is None:
        raise ValueError("v2_golden_core_missing")
    # 相同输入、实际事件与任务结果必须一致；墙钟耗时和输出目录不是实验结果。
    return canonical_digest((core.data.facts, core.data.proof.task))
