"""T10 声明式 checkpoint 与成对反事实重放入口。"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from skillflow.benchmark.manifests import load_manifests
from skillflow.benchmark.replay_analysis import ReplayAnalysisSetup, analyze_replay_pair
from skillflow.benchmark.replay_branch import (
    ReplayBranchSetup,
    ReplayRuntimeConfig,
    ReplaySourceSetup,
    capture_replay_source,
    run_replay_branch,
)
from skillflow.benchmark.replay_fingerprint import (
    ReplayFingerprintSetup,
    build_control_evidence,
)
from skillflow.benchmark.replay_models import ReplayBatchResult, ReplayPairResult
from skillflow.benchmark.replay_output import write_replay_outputs
from skillflow.benchmark.scripted_backend import FixtureScript
from skillflow.instrumentation.artifact_intervention import ArtifactInterventionMode
from skillflow.models.enums import Decision
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import CounterfactualSpec, EffectSelector
from skillflow.validation import validate_yaml_document


@dataclass(frozen=True, slots=True)
class ReplayPairSetup:
    """一个预注册反事实的确定性编排输入。"""

    index: int
    counterfactual: CounterfactualSpec
    selector: EffectSelector
    runtime: ReplayRuntimeConfig
    pair_root: Path


class ReplayRunner:
    """从同一 checkpoint 创建 identity/neutral 两条隔离分支。"""

    def __init__(
        self,
        scripts: Mapping[str, FixtureScript],
        decisions: Mapping[str, Decision],
    ) -> None:
        """复制白名单 Script 与结构决策，避免调用方运行中修改。"""
        self._scripts = dict(scripts)
        self._decisions = dict(decisions)

    def run(self, scenario_path: Path, replay_root: Path, seed: str) -> ReplayBatchResult:
        """验证 Scenario，并按声明顺序执行全部成对反事实。"""
        scenario = validate_yaml_document(scenario_path, Scenario)
        manifests = load_manifests(scenario_path, scenario)
        runtime = ReplayRuntimeConfig(
            scenario=scenario,
            scripts=self._scripts,
            decisions=self._decisions,
            manifests=manifests,
            seed=seed,
        )
        selectors = {selector.alias: selector for selector in scenario.effect_selectors}
        replay_root.mkdir(parents=True, exist_ok=False)
        pairs = tuple(
            self._run_pair(
                ReplayPairSetup(
                    index=index,
                    counterfactual=counterfactual,
                    selector=selectors[counterfactual.observe.alias],
                    runtime=runtime,
                    pair_root=replay_root / f"pair-{index:02d}-{counterfactual.target.alias}",
                )
            )
            for index, counterfactual in enumerate(scenario.counterfactuals, start=1)
        )
        return ReplayBatchResult(scenario.id, pairs)

    def _run_pair(self, setup: ReplayPairSetup) -> ReplayPairResult:
        counterfactual = setup.counterfactual
        target_alias = counterfactual.target.alias
        scenario = setup.runtime.scenario
        replay_id = f"replay-{scenario.id}-{setup.index:02d}-{target_alias}"
        source_run_id = f"run-{scenario.id}-cf{setup.index:02d}-source"
        original_run_id = f"run-{scenario.id}-cf{setup.index:02d}-original"
        neutral_run_id = f"run-{scenario.id}-cf{setup.index:02d}-neutral"
        setup.pair_root.mkdir(parents=True, exist_ok=False)
        source = capture_replay_source(
            ReplaySourceSetup(
                setup.runtime,
                source_run_id,
                setup.pair_root / "source",
                target_alias,
            )
        )
        original = run_replay_branch(
            ReplayBranchSetup(
                setup.runtime,
                original_run_id,
                setup.pair_root / "original",
                target_alias,
                source,
                ArtifactInterventionMode.IDENTITY,
            )
        )
        neutral = run_replay_branch(
            ReplayBranchSetup(
                setup.runtime,
                neutral_run_id,
                setup.pair_root / "neutral",
                target_alias,
                source,
                ArtifactInterventionMode.NEUTRAL,
            )
        )
        controls = build_control_evidence(
            ReplayFingerprintSetup(
                scenario,
                setup.runtime.scripts,
                setup.runtime.decisions,
                setup.runtime.manifests,
                setup.runtime.seed,
                source.checkpoint,
            )
        )
        analyzed = analyze_replay_pair(
            ReplayAnalysisSetup(
                replay_id,
                target_alias,
                source,
                original,
                neutral,
                setup.selector,
                controls,
            )
        )
        report_path, manifest_path = write_replay_outputs(
            setup.pair_root,
            analyzed.report,
            analyzed.manifest,
        )
        return ReplayPairResult(
            target_alias=target_alias,
            report=analyzed.report,
            report_path=report_path,
            manifest_path=manifest_path,
            checkpoint=source.checkpoint,
            original_restore_state_hash=original.restore_state_hash,
            neutral_restore_state_hash=neutral.restore_state_hash,
            original_prefix_hash=original.prefix_hash,
            neutral_prefix_hash=neutral.prefix_hash,
            original_intervention=original.intervention,
            neutral_intervention=neutral.intervention,
            original_pre_intervention_skill_state=original.pre_intervention_skill_state,
            neutral_pre_intervention_skill_state=neutral.pre_intervention_skill_state,
        )
