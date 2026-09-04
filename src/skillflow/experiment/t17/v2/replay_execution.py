"""从同一次 core 的实际检查点执行两条分支，不补采源前缀。"""

from pathlib import Path

from skillflow.benchmark.manifests import load_manifests
from skillflow.benchmark.replay_analysis import ReplayAnalysisSetup, analyze_replay_pair
from skillflow.benchmark.replay_branch import (
    ReplayBranchSetup,
    ReplayRuntimeConfig,
    run_replay_branch,
)
from skillflow.benchmark.replay_fingerprint import ReplayFingerprintSetup, build_control_evidence
from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.minimal.raw_validation import restore_run_receipts
from skillflow.experiment.t17.v2.config_models import V2Trial
from skillflow.experiment.t17.v2.portable import capture_run
from skillflow.experiment.t17.v2.portable_models import PortableRun
from skillflow.experiment.t17.v2.replay_proof import build_replay_proof, source_facts
from skillflow.experiment.t17.v2.run_models import ReplayTerminal
from skillflow.experiment.t17.v2.runtime import V2HarnessFactory
from skillflow.experiment.t17.v2.stage_contract import unit_identity
from skillflow.experiment.t17.v2.unit_execution import (
    CoreExecution,
    ExecutionContext,
    compact_id,
    file_inventory,
)
from skillflow.instrumentation.artifact_intervention import ArtifactInterventionMode
from skillflow.store.sqlite_store import SqliteEventStore


def execute_replay(
    context: ExecutionContext, trial: V2Trial, core: CoreExecution, alias: str
) -> ReplayTerminal:
    """缺失目标保留真实 core 证据；其他情况必须完成共享前缀的两分支。"""
    unit_id = trial.replay_pair_ids[alias]
    identity = unit_identity(context.phase, context.matrix, trial, unit_id)
    source = core.capture.checkpoints.get(alias)
    empty_target = source is not None and any(
        item.artifact.artifact_id == source.source_artifact_id
        and item.artifact.content_length == 0
        and item.artifact.content_hash
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        for item in source.checkpoint.store.artifacts
    )
    if source is None or empty_target:
        if core.terminal.data is None:
            raise ValueError("v2_replay_core_evidence_missing")
        return ReplayTerminal(
            identity=identity,
            source_core_run_id=core.terminal.run_id,
            target_alias=alias,
            status="not_applicable",
            reason="target_empty_no_neutral_form" if empty_target else "target_not_produced",
            absent_source=core.terminal.data.facts,
            issues=tuple(core.capture.issues),
        )
    if source.checkpoint.source_run_id != core.terminal.run_id:
        raise ValueError("v2_replay_core_checkpoint_binding")
    counterfactual = next(c for c in core.scenario.counterfactuals if c.target.alias == alias)
    selector = next(
        s for s in core.scenario.effect_selectors if s.alias == counterfactual.observe.alias
    )
    factory = V2HarnessFactory(context.client, trial.task_prompt, capture_checkpoints=False)
    manifests = load_manifests(core.scenario_path, core.scenario)
    runtime = ReplayRuntimeConfig(
        core.scenario,
        core.bundle.scripts,
        core.bundle.decisions,
        manifests,
        core.seed,
        factory,
        factory.execution_policy.factory,
    )
    directory = context.output / "replay" / compact_id(unit_id)
    directory.mkdir(parents=True, exist_ok=False)
    original_id = "run-" + compact_id(unit_id + ":original")
    neutral_id = "run-" + compact_id(unit_id + ":neutral")
    original = run_replay_branch(
        ReplayBranchSetup(
            runtime, original_id, directory / "o", alias, source, ArtifactInterventionMode.IDENTITY
        )
    )
    neutral = run_replay_branch(
        ReplayBranchSetup(
            runtime, neutral_id, directory / "n", alias, source, ArtifactInterventionMode.NEUTRAL
        )
    )
    controls = build_control_evidence(
        ReplayFingerprintSetup(
            core.scenario,
            core.bundle.scripts,
            core.bundle.decisions,
            manifests,
            core.seed,
            source.checkpoint,
        )
    )
    analyzed = analyze_replay_pair(
        ReplayAnalysisSetup(
            unit_id,
            alias,
            source,
            original,
            neutral,
            selector,
            controls,
            context.output.name,
            core.terminal.run_id,
            trial.configuration.scenario,
            redacted=True,
        )
    )
    write_checked_json(directory / "legacy-replay-report.json", analyzed.report)
    write_checked_json(directory / "pair-manifest.json", analyzed.manifest)
    proof = build_replay_proof(
        source_facts(source),
        _branch_facts(directory / "o", original_id),
        _branch_facts(directory / "n", neutral_id),
        selector,
        analyzed.manifest,
    )
    write_checked_json(directory / "portable-replay.json", proof)
    return ReplayTerminal(
        identity=identity,
        source_core_run_id=core.terminal.run_id,
        target_alias=alias,
        status="completed",
        proof=proof,
        decisions=tuple(d for c in factory.captures.values() for d in c.decisions),
        issues=tuple(i for c in factory.captures.values() for i in c.issues),
        raw_files=file_inventory(context.output, directory),
    )


def _branch_facts(root: Path, run_id: str) -> PortableRun:
    with SqliteEventStore(root / "state.sqlite") as store:
        return capture_run(store, run_id, restore_run_receipts(store, root, run_id))
