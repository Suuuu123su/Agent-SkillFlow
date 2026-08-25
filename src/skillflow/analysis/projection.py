"""把双轨 Trace 与 SecurityGraph 投影为 T09 中立事实。"""

from dataclasses import dataclass
from typing import TypeVar, assert_never

from skillflow.analysis.errors import AnalysisInvariantError
from skillflow.analysis.facts import (
    EffectMetricSample,
    ProvenanceSample,
    ScenarioMetricFacts,
)
from skillflow.graph.models import SecurityPath
from skillflow.graph.security import SecurityGraph
from skillflow.models.metrics import EffectPathEvidence
from skillflow.oracle.models import (
    OracleArtifactTrace,
    OracleEffectTrace,
    OracleTraceRecord,
)
from skillflow.trace.contracts import TraceValueType
from skillflow.trace.observed import (
    ObservedArtifactTrace,
    ObservedEffectTrace,
    ObservedTraceRecord,
)

_RecordT = TypeVar("_RecordT")


@dataclass(frozen=True, slots=True)
class RunTraceAnalysisInput:
    """一次 Run 的双轨记录、图和稳定身份。"""

    scenario_id: str
    run_id: str
    observed_records: tuple[ObservedTraceRecord, ...]
    oracle_records: tuple[OracleTraceRecord, ...]
    graph: SecurityGraph


def project_scenario_facts(run: RunTraceAnalysisInput) -> ScenarioMetricFacts:
    """只用 Oracle 真值、真实 Receipt 与脱敏图生成指标输入。"""
    observed_artifacts, observed_effects = _index_observed(run)
    oracle_artifacts, oracle_effects = _index_oracle(run)
    if set(observed_effects) != set(oracle_effects):
        raise AnalysisInvariantError(
            "project_effects",
            "Observed 与 Oracle 的 Receipt Effect 集合不一致",
        )
    effects = tuple(
        _effect_sample(record, observed_effects[effect_id], run.graph)
        for effect_id, record in oracle_effects.items()
    )
    observed_artifact_ids = set(observed_artifacts)
    oracle_runtime_artifact_ids = {
        artifact_id
        for artifact_id, record in oracle_artifacts.items()
        if record.value_type is not TraceValueType.ASSET
    }
    if observed_artifact_ids != oracle_runtime_artifact_ids:
        missing_observed = sorted(oracle_runtime_artifact_ids - observed_artifact_ids)
        missing_oracle = sorted(observed_artifact_ids - oracle_runtime_artifact_ids)
        raise AnalysisInvariantError(
            "project_provenance",
            "双轨运行 Artifact 集合不一致："
            f"Observed 缺少 {missing_observed}；Oracle 缺少 {missing_oracle}",
        )
    provenance: list[ProvenanceSample] = []
    for artifact_id, observed in observed_artifacts.items():
        oracle = oracle_artifacts[artifact_id]
        provenance.append(_provenance_sample(observed, oracle, run.graph))
    return ScenarioMetricFacts(
        scenario_id=run.scenario_id,
        run_id=run.run_id,
        effects=effects,
        provenance=tuple(provenance),
    )


def _index_observed(
    run: RunTraceAnalysisInput,
) -> tuple[dict[str, ObservedArtifactTrace], dict[str, ObservedEffectTrace]]:
    artifacts: dict[str, ObservedArtifactTrace] = {}
    effects: dict[str, ObservedEffectTrace] = {}
    for record in run.observed_records:
        _require_run_id(record.run_id, run.run_id, "Observed")
        match record:
            case ObservedArtifactTrace():
                _add_unique(artifacts, record.artifact_id, record)
            case ObservedEffectTrace():
                _add_unique(effects, record.effect_id, record)
            case _ as unreachable:
                assert_never(unreachable)
    return artifacts, effects


def _index_oracle(
    run: RunTraceAnalysisInput,
) -> tuple[dict[str, OracleArtifactTrace], dict[str, OracleEffectTrace]]:
    artifacts: dict[str, OracleArtifactTrace] = {}
    effects: dict[str, OracleEffectTrace] = {}
    for record in run.oracle_records:
        _require_run_id(record.run_id, run.run_id, "Oracle")
        match record:
            case OracleArtifactTrace():
                _add_unique(artifacts, record.artifact_id, record)
            case OracleEffectTrace():
                _add_unique(effects, record.effect_id, record)
            case _ as unreachable:
                assert_never(unreachable)
    return artifacts, effects


def _effect_sample(
    oracle: OracleEffectTrace,
    observed: ObservedEffectTrace,
    graph: SecurityGraph,
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
        _path_evidence(path) for path in graph.find_paths(oracle.actor_id, oracle.effect_id)
    )
    if oracle.gt_effect and not oracle.gt_auth and not paths:
        raise AnalysisInvariantError(
            "project_effects",
            f"未授权已执行 Effect 缺少来源到落点路径：{oracle.effect_id}",
        )
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


def _provenance_sample(
    observed: ObservedArtifactTrace,
    oracle: OracleArtifactTrace,
    graph: SecurityGraph,
) -> ProvenanceSample:
    if observed.value_type is not oracle.value_type:
        raise AnalysisInvariantError(
            "project_provenance",
            f"Artifact value_type 不一致：{observed.artifact_id}",
        )
    paths = graph.find_ancestors(observed.artifact_id)
    return ProvenanceSample(
        artifact_id=observed.artifact_id,
        boundary_depth=max(
            (path.boundary_depth.total for path in paths),
            default=0,
        ),
        observed_origins=frozenset(observed.observed_data),
        oracle_origins=frozenset(oracle.gt_data),
        evidence_event_ids=_unique(
            (
                observed.event_id,
                *(event_id for path in paths for event_id in path.evidence_event_ids),
            )
        ),
    )


def _path_evidence(path: SecurityPath) -> EffectPathEvidence:
    return EffectPathEvidence(
        node_ids=tuple(
            f"{reference.kind.value}:{reference.node_id}" for reference in path.node_refs
        ),
        evidence_event_ids=path.evidence_event_ids,
        boundary_depth=path.boundary_depth,
    )


def _require_run_id(actual: str, expected: str, plane: str) -> None:
    if actual != expected:
        raise AnalysisInvariantError(
            "project_run",
            f"{plane} record 的 run_id 不一致：{actual}",
        )


def _add_unique(
    records: dict[str, _RecordT],
    record_id: str,
    record: _RecordT,
) -> None:
    if record_id in records:
        raise AnalysisInvariantError(
            "project_trace",
            f"{type(record).__name__} ID 重复：{record_id}",
        )
    records[record_id] = record


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
