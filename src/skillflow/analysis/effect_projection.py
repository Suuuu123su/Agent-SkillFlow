"""把双轨 Effect、Decision 与图路径投影为可聚合事实。"""

from dataclasses import dataclass

from skillflow.analysis.effect_selection import effect_matches_selector
from skillflow.analysis.errors import AnalysisInvariantError
from skillflow.analysis.facts import EffectMetricSample
from skillflow.graph.models import SecurityPath
from skillflow.graph.security import SecurityGraph
from skillflow.models.effects import EffectRecord
from skillflow.models.events import DecisionRecord
from skillflow.models.metrics import EffectPathEvidence
from skillflow.models.provenance import Artifact
from skillflow.models.run_results import DecisionBasisArtifact
from skillflow.models.scenario import Scenario
from skillflow.oracle.models import OracleEffectTrace
from skillflow.trace.observed import ObservedArtifactTrace, ObservedEffectTrace


@dataclass(frozen=True, slots=True)
class EffectAnalysisEvidence:
    """EventStore 为一个 Effect 提供的完整 Decision 边界事实。"""

    effect: EffectRecord
    decision: DecisionRecord
    basis_artifacts: tuple[Artifact, ...]


@dataclass(frozen=True, slots=True)
class _ProjectionContext:
    graph: SecurityGraph
    evidence_by_effect: dict[str, EffectAnalysisEvidence]
    scenario: Scenario | None
    observed_artifacts: dict[str, ObservedArtifactTrace]


@dataclass(frozen=True, slots=True)
class EffectProjectionInput:
    """一次 Effect 投影所需的双轨记录与运行证据。"""

    oracle_effects: dict[str, OracleEffectTrace]
    observed_effects: dict[str, ObservedEffectTrace]
    graph: SecurityGraph
    evidence: tuple[EffectAnalysisEvidence, ...]
    scenario: Scenario | None
    observed_artifacts: dict[str, ObservedArtifactTrace]


def project_effect_samples(source: EffectProjectionInput) -> tuple[EffectMetricSample, ...]:
    """校验双轨 Effect 一致性并关联决策、Receipt 与来源到落点路径。"""
    context = _ProjectionContext(
        source.graph,
        _unique_effect_evidence(source.evidence),
        source.scenario,
        source.observed_artifacts,
    )
    return tuple(
        _effect_sample(record, source.observed_effects[effect_id], context)
        for effect_id, record in source.oracle_effects.items()
    )


def _effect_sample(
    oracle: OracleEffectTrace,
    observed: ObservedEffectTrace,
    context: _ProjectionContext,
) -> EffectMetricSample:
    if (
        oracle.receipt_id != observed.receipt_id
        or oracle.actor_id != observed.actor_id
        or oracle.action_id != observed.action_id
        or oracle.call_id != observed.call_id
        or oracle.effect != observed.effect
        or oracle.gt_effect != observed.observed_effect
    ):
        raise AnalysisInvariantError(
            "project_effects",
            f"Observed 与 Oracle Effect 绑定冲突：{oracle.effect_id}",
        )
    paths = tuple(
        _path_evidence(path) for path in context.graph.find_paths(oracle.actor_id, oracle.effect_id)
    )
    if oracle.gt_effect and not oracle.gt_auth and not paths:
        raise AnalysisInvariantError(
            "project_effects",
            f"未授权已执行 Effect 缺少来源到落点路径：{oracle.effect_id}",
        )
    evidence = context.evidence_by_effect.get(oracle.effect_id)
    if evidence is None:
        return EffectMetricSample(
            effect_id=oracle.effect_id,
            receipt_id=oracle.receipt_id,
            decision_id=observed.decision_id,
            effect=oracle.effect,
            executed=oracle.gt_effect,
            authorized=oracle.gt_auth,
            manifest_declared=oracle.manifest_declared,
            matched_grant_ids=oracle.matched_grant_ids,
            paths=paths,
        )
    decision = evidence.decision
    return EffectMetricSample(
        effect_id=oracle.effect_id,
        receipt_id=oracle.receipt_id,
        decision_id=observed.decision_id,
        effect=oracle.effect,
        executed=oracle.gt_effect,
        authorized=oracle.gt_auth,
        manifest_declared=oracle.manifest_declared,
        matched_grant_ids=oracle.matched_grant_ids,
        paths=paths,
        effect_alias=evidence.effect.effect_alias,
        selector_aliases=_selector_aliases(evidence.effect, context.scenario),
        action_id=observed.action_id,
        request_event_id=evidence.effect.request_event_id,
        actor_id=observed.actor_id,
        session_id=observed.session_id,
        session_index=_session_index(observed.session_id, context.scenario),
        timestamp=observed.timestamp,
        baseline_result=decision.baseline_result,
        policy_result=decision.policy_result,
        decision_basis_artifacts=tuple(
            DecisionBasisArtifact(
                artifact_id=artifact.artifact_id,
                aliases=tuple(
                    alias.removeprefix("artifact:")
                    for alias in (
                        ()
                        if artifact.artifact_id not in context.observed_artifacts
                        else context.observed_artifacts[artifact.artifact_id].aliases
                    )
                ),
                trust=artifact.observed_label.trust,
            )
            for artifact in evidence.basis_artifacts
        ),
        reason_codes=decision.reason_codes,
    )


def _unique_effect_evidence(
    values: tuple[EffectAnalysisEvidence, ...],
) -> dict[str, EffectAnalysisEvidence]:
    indexed: dict[str, EffectAnalysisEvidence] = {}
    for value in values:
        effect_id = value.effect.effect_id
        previous = indexed.get(effect_id)
        if previous is not None and previous != value:
            raise AnalysisInvariantError(
                "project_effects",
                f"同一 Effect 出现冲突运行证据：{effect_id}",
            )
        indexed[effect_id] = value
    return indexed


def _selector_aliases(effect: EffectRecord, scenario: Scenario | None) -> tuple[str, ...]:
    if scenario is None:
        return ()
    return tuple(
        selector.alias
        for selector in scenario.effect_selectors
        if effect_matches_selector(effect, selector)
    )


def _session_index(session_id: str, scenario: Scenario | None) -> int:
    if scenario is None:
        return 0
    for index, session in enumerate(scenario.sessions):
        if session.id == session_id:
            return index
    raise AnalysisInvariantError(
        "project_effects",
        f"Effect 引用了 Scenario 外 Session：{session_id}",
    )


def _path_evidence(path: SecurityPath) -> EffectPathEvidence:
    return EffectPathEvidence(
        node_ids=tuple(
            f"{reference.kind.value}:{reference.node_id}" for reference in path.node_refs
        ),
        evidence_event_ids=path.evidence_event_ids,
        boundary_depth=path.boundary_depth,
    )
