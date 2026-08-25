"""Matrix 核心 Run 的隔离确定性重复检查。"""

import hashlib

from skillflow.benchmark.runner import (
    ScenarioRunLayout,
    ScenarioRunner,
    ScenarioRunRequest,
    ScenarioRunResult,
)
from skillflow.experiment.inputs import selected_harm_selector, slug
from skillflow.experiment.layout import ExperimentLayout
from skillflow.experiment.matrix_support import ExecutedVariant, build_run_metadata
from skillflow.experiment.run_artifacts import require_mock_only
from skillflow.models.execution import DeterminismCheck
from skillflow.models.matrix_axes import MatrixRunRole


def check_determinism(
    item: ExecutedVariant,
    layout: ExperimentLayout,
    experiment_id: str,
    repeats: int,
    runner: ScenarioRunner,
) -> DeterminismCheck:
    """在 blobs 下运行副本；副本永不进入核心 Run 集合或聚合。"""
    expected = _fingerprint(item.result)
    observed = [expected]
    for index in range(2, repeats + 1):
        root = (
            layout.root / "blobs" / "determinism" / slug(item.variant.variant) / f"repeat-{index}"
        )
        repeat_layout = ScenarioRunLayout(
            run_root=root / "run",
            experiment_root=root,
            database_path=root / "state.sqlite",
            workspace_root=root / "workspace",
            security_graph_path=root / "run" / "graph.json",
            risk_report_path=root / "run" / "run-report.json",
        )
        selector = item.variant.harm_selector or selected_harm_selector(item.scenario)
        repeated = runner.run_configured(
            ScenarioRunRequest(
                scenario_path=item.scenario_path,
                scenario=item.scenario,
                run_id=item.result.run_id,
                id_seed=f"{item.result.run_id}:{item.variant.seed}",
                layout=repeat_layout,
                report_metadata=build_run_metadata(
                    experiment_id,
                    item.variant,
                    selector
                    if item.variant.harm_selector is not None or item.scenario.harm_selector
                    else None,
                    item.result.risk_report.redacted,
                    MatrixRunRole.DETERMINISM_REPEAT,
                ),
            )
        )
        require_mock_only(repeated)
        observed.append(_fingerprint(repeated))
    return DeterminismCheck(
        run_id=item.result.run_id,
        repeats=repeats,
        consistent=len(set(observed)) == 1,
        fingerprint=expected,
    )


def _fingerprint(result: ScenarioRunResult) -> str:
    digest = hashlib.sha256()
    for path in (
        result.observed_trace_path,
        result.oracle_trace_path,
        result.security_graph_path,
    ):
        digest.update(path.read_bytes())
    normalized = result.risk_report.model_copy(update={"run_role": MatrixRunRole.CORE})
    digest.update(normalized.model_dump_json(by_alias=True).encode())
    return digest.hexdigest()
