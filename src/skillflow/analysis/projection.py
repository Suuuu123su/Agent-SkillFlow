"""把双轨 Trace 与 SecurityGraph 投影为 T09 中立事实。"""

from dataclasses import dataclass, field
from typing import TypeVar, assert_never

from skillflow.analysis.effect_projection import (
    EffectAnalysisEvidence,
    EffectProjectionInput,
    project_effect_samples,
)
from skillflow.analysis.errors import AnalysisInvariantError
from skillflow.analysis.facts import (
    ProvenanceSample,
    RunReportMetadata,
    ScenarioMetricFacts,
)
from skillflow.graph.security import SecurityGraph
from skillflow.models.provenance import Artifact
from skillflow.models.run_results import (
    ArtifactAliasEvidence,
    RunRevocationEvidence,
)
from skillflow.models.scenario import Scenario
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
    task_success: bool | None = None
    scenario_definition: Scenario | None = None
    metadata: RunReportMetadata = field(default_factory=RunReportMetadata)
    effect_evidence: tuple[EffectAnalysisEvidence, ...] = ()
    runtime_artifacts: tuple[Artifact, ...] = ()
    revocations: tuple[RunRevocationEvidence, ...] = ()
    allow_absent_counterfactuals: bool = False


def project_scenario_facts(run: RunTraceAnalysisInput) -> ScenarioMetricFacts:
    """只用 Oracle 真值、真实 Receipt 与脱敏图生成指标输入。"""
    observed_artifacts, observed_effects = _index_observed(run)
    oracle_artifacts, oracle_effects = _index_oracle(run)
    if set(observed_effects) != set(oracle_effects):
        raise AnalysisInvariantError(
            "project_effects",
            "Observed 与 Oracle 的 Receipt Effect 集合不一致",
        )
    effects = project_effect_samples(
        EffectProjectionInput(
            oracle_effects,
            observed_effects,
            run.graph,
            run.effect_evidence,
            run.scenario_definition,
            observed_artifacts,
        )
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
        task_success=run.task_success,
        metadata=run.metadata,
        counterfactual_artifacts=_counterfactual_artifacts(run, observed_artifacts),
        revocations=run.revocations,
        rir_check_offsets=_rir_check_offsets(run.scenario_definition),
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


def _counterfactual_artifacts(
    run: RunTraceAnalysisInput,
    observed: dict[str, ObservedArtifactTrace],
) -> tuple[ArtifactAliasEvidence, ...]:
    scenario = run.scenario_definition
    if scenario is None:
        return ()
    runtime = {artifact.artifact_id: artifact for artifact in run.runtime_artifacts}
    by_alias = {
        alias.removeprefix("artifact:"): record.artifact_id
        for record in observed.values()
        for alias in record.aliases
    }
    values: list[ArtifactAliasEvidence] = []
    for counterfactual in scenario.counterfactuals:
        alias = counterfactual.target.alias
        artifact_id = by_alias.get(alias)
        if artifact_id is None and run.allow_absent_counterfactuals:
            continue
        if artifact_id is None or artifact_id not in runtime:
            raise AnalysisInvariantError(
                "project_counterfactual",
                f"反事实 alias 缺少运行 Artifact：{alias}",
            )
        values.append(
            ArtifactAliasEvidence(
                alias=alias,
                artifact_id=artifact_id,
                trust=runtime[artifact_id].observed_label.trust,
            )
        )
    return tuple(values)


def _rir_check_offsets(scenario: Scenario | None) -> tuple[int, ...]:
    if scenario is None or scenario.oracle.expected_persistence is None:
        return ()
    return scenario.oracle.expected_persistence.check_offsets


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
