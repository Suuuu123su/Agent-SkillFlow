"""本地实际检查点成对重放；在线归因与事后测量均消耗同一固定名额。"""

from dataclasses import dataclass, field
from pathlib import Path

from skillflow.benchmark.manifests import load_manifests
from skillflow.benchmark.replay_analysis import ReplayAnalysisSetup, analyze_replay_pair
from skillflow.benchmark.replay_branch import (
    ReplayBranchSetup,
    ReplayRuntimeConfig,
    run_replay_branch,
)
from skillflow.benchmark.replay_fingerprint import ReplayFingerprintSetup, build_control_evidence
from skillflow.benchmark.replay_models import ReplaySourceState
from skillflow.defense.signals import SignalProjection
from skillflow.defense.task_plan import CausalAssessment
from skillflow.experiment.t17.minimal.raw_validation import restore_run_receipts
from skillflow.experiment.t17.v2.portable import capture_run
from skillflow.experiment.t17.v2.portable_models import PortableRun
from skillflow.experiment.t17.v2.replay_proof import build_replay_proof, source_facts
from skillflow.experiment.t17.v2.run_models import ReplayProof
from skillflow.experiment.t18.catalog_models import LocalSkill
from skillflow.experiment.t18.matrix import CoreCell, Domain
from skillflow.experiment.t18.planning import matches
from skillflow.experiment.t18.runtime import LocalHarnessFactory
from skillflow.instrumentation.artifact_intervention import ArtifactInterventionMode
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.scenario import Scenario
from skillflow.policy.runtime import PolicyToolRequest
from skillflow.store.sqlite_store import SqliteEventStore


class LocalReplay(StrictModel):
    """一对实际分支的可独立复算证明，不计入核心任务分母。"""

    pair_id: NonEmptyStr
    domain: Domain
    trial_id: NonEmptyStr
    source_run_id: NonEmptyStr
    target_alias: NonEmptyStr
    online: bool
    proof: ReplayProof
    fake_calls: int


@dataclass(slots=True)
class ReplayBudget:
    """只允许同域固定数量的独立对；使用过的名额不回收。"""

    maximum: int
    used: int = 0

    def reserve(self) -> int:
        """开分支前登记，达到上限立即拒绝，不偷偷扩容。"""
        if self.used >= self.maximum:
            raise ValueError("t18_replay_budget_exhausted")
        self.used += 1
        return self.used


@dataclass(slots=True)
class ReplayCoordinator:
    """绑定一个核心运行和其现场检查点，不能借用其他模式或任务结果。"""

    project_root: Path
    output: Path
    skill: LocalSkill
    cell: CoreCell
    scenario: Scenario
    factory: LocalHarnessFactory
    run_id: str
    budget: ReplayBudget
    records: list[LocalReplay] = field(default_factory=list)

    def online(self, request: PolicyToolRequest, projection: SignalProjection) -> CausalAssessment:
        """只选当前请求的来源祖先和同效果选择器，拒绝无关来源重放。"""
        checkpoints = self.factory.captures[self.run_id].checkpoints
        selector_by_alias = {s.alias: s for s in self.scenario.effect_selectors}
        for candidate in self.scenario.counterfactuals:
            source = checkpoints.get(candidate.target.alias)
            if (
                source is not None
                and source.source_artifact_id in projection.memory_artifact_ids
                and matches(request.effect, selector_by_alias[candidate.observe.alias])
            ):
                record = self.run_pair(candidate.target.alias, online=True)
                proof = record.proof
                return CausalAssessment(
                    status="measured",
                    reason="same_checkpoint_receipted_effect_difference",
                    pair_id=record.pair_id,
                    y_original=proof.y_original,
                    y_neutral=proof.y_neutral,
                    ci=proof.ci,
                    evidence_ids=proof.evidence_ids,
                )
        return CausalAssessment(
            status="not_available",
            reason="matching_checkpoint_missing",
            evidence_ids=projection.signals.evidence_ids,
        )

    def run_pair(self, alias: str, *, online: bool) -> LocalReplay:
        """同核心同来源只计一次；同名但不同运行不能复用。"""
        previous = next((r for r in self.records if r.target_alias == alias), None)
        if previous is not None:
            return previous
        source = self.factory.captures[self.run_id].checkpoints[alias]
        if source.checkpoint.source_run_id != self.run_id:
            raise ValueError("t18_replay_source_run_mismatch")
        number = self.budget.reserve()
        path = self.output / "replay" / f"p{number:03d}"
        path.mkdir(parents=True, exist_ok=False)
        record = self._execute(alias, source, path, online=online)
        with (path / "portable-replay.json").open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(record.model_dump_json(indent=2) + "\n")
        self.records.append(record)
        return record

    def _execute(
        self, alias: str, source: ReplaySourceState, directory: Path, *, online: bool
    ) -> LocalReplay:
        counterfactual = next(c for c in self.scenario.counterfactuals if c.target.alias == alias)
        selector = next(
            s for s in self.scenario.effect_selectors if s.alias == counterfactual.observe.alias
        )
        factory = LocalHarnessFactory(self.skill, self.cell.mode, self.factory.domain, shadow=True)
        manifests = load_manifests(self.project_root / self.skill.scenario_path, self.scenario)
        runtime = ReplayRuntimeConfig(
            self.scenario,
            self.skill.bundle.scripts,
            self.skill.bundle.decisions,
            manifests,
            self.cell.seed,
            factory,
            factory.execution_policy.factory,
        )
        pair_id = self.run_id + ":replay:" + alias
        original_id, neutral_id = pair_id + ":original", pair_id + ":neutral"
        original = run_replay_branch(
            ReplayBranchSetup(
                runtime,
                original_id,
                directory / "o",
                alias,
                source,
                ArtifactInterventionMode.IDENTITY,
            )
        )
        neutral = run_replay_branch(
            ReplayBranchSetup(
                runtime,
                neutral_id,
                directory / "n",
                alias,
                source,
                ArtifactInterventionMode.NEUTRAL,
            )
        )
        controls = build_control_evidence(
            ReplayFingerprintSetup(
                self.scenario,
                self.skill.bundle.scripts,
                self.skill.bundle.decisions,
                manifests,
                self.cell.seed,
                source.checkpoint,
            )
        )
        analyzed = analyze_replay_pair(
            ReplayAnalysisSetup(
                pair_id,
                alias,
                source,
                original,
                neutral,
                selector,
                controls,
                source_run_id=self.run_id,
            )
        )
        proof = build_replay_proof(
            source_facts(source),
            _branch(directory / "o", original_id),
            _branch(directory / "n", neutral_id),
            selector,
            analyzed.manifest,
        )
        return LocalReplay(
            pair_id=pair_id,
            domain=self.factory.domain,
            trial_id=self.cell.trial_id,
            source_run_id=self.run_id,
            target_alias=alias,
            online=online,
            proof=proof,
            fake_calls=sum(len(c.decisions) for c in factory.captures.values()),
        )


def _branch(root: Path, run_id: str) -> PortableRun:
    with SqliteEventStore(root / "state.sqlite") as store:
        return capture_run(store, run_id, restore_run_receipts(store, root, run_id))
