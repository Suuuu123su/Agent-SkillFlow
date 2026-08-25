import pytest

from skillflow.analysis.errors import AnalysisInvariantError
from skillflow.analysis.projection import (
    RunTraceAnalysisInput,
    project_scenario_facts,
)
from skillflow.graph.models import GraphBuildData
from skillflow.graph.security import SecurityGraph
from skillflow.oracle.models import OracleArtifactTrace
from skillflow.trace.contracts import TraceValueType
from skillflow.trace.observed import ObservedArtifactTrace


def empty_graph(run_id: str) -> SecurityGraph:
    return SecurityGraph(
        GraphBuildData(
            run_id=run_id,
            nodes=(),
            provenance_edges=(),
            security_edges=(),
            revocations=(),
        )
    )


def analysis_input(
    observed: tuple[ObservedArtifactTrace, ...],
    oracle: tuple[OracleArtifactTrace, ...],
) -> RunTraceAnalysisInput:
    return RunTraceAnalysisInput(
        scenario_id="scenario-1",
        run_id="run-1",
        observed_records=observed,
        oracle_records=oracle,
        graph=empty_graph("run-1"),
    )


def observed_artifact() -> ObservedArtifactTrace:
    return ObservedArtifactTrace(
        run_id="run-1",
        artifact_id="artifact-1",
        value_type=TraceValueType.FILE,
        event_id="event-1",
        observed_data=("A",),
        parents=(),
    )


def oracle_artifact(value_type: TraceValueType) -> OracleArtifactTrace:
    artifact_id = "asset:root" if value_type is TraceValueType.ASSET else "artifact-1"
    return OracleArtifactTrace(
        run_id="run-1",
        artifact_id=artifact_id,
        value_type=value_type,
        gt_data=("A",),
        parents=(),
    )


def test_projection_rejects_observed_artifact_without_oracle_pair() -> None:
    with pytest.raises(AnalysisInvariantError) as captured:
        project_scenario_facts(analysis_input((observed_artifact(),), ()))

    assert captured.value.operation == "project_provenance"


def test_projection_rejects_missing_observed_runtime_artifact() -> None:
    with pytest.raises(AnalysisInvariantError) as captured:
        project_scenario_facts(analysis_input((), (oracle_artifact(TraceValueType.FILE),)))

    assert captured.value.operation == "project_provenance"


def test_projection_allows_oracle_only_declarative_asset_root() -> None:
    facts = project_scenario_facts(analysis_input((), (oracle_artifact(TraceValueType.ASSET),)))

    assert facts.provenance == ()
