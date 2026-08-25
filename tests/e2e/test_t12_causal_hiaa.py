import shutil
from pathlib import Path

import yaml

from skillflow.analysis.hiaa import MatrixRunOutcome, calculate_hiaa
from skillflow.benchmark.replay import ReplayRunner
from skillflow.benchmark.runner import ScenarioRunner, ScenarioRunResult
from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import EffectSelector
from skillflow.store.sqlite_store import SqliteEventStore
from skillflow.validation import validate_yaml_document

ROOT = Path("scenarios")


def _runner() -> ScenarioRunner:
    scripts, decisions = t12_fixture_registry()
    return ScenarioRunner(scripts, decisions)


def _replay_runner() -> ReplayRunner:
    scripts, decisions = t12_fixture_registry()
    return ReplayRunner(scripts, decisions)


def _copy_variant(source: Path, root: Path, shared_context: bool) -> Path:
    scenario = validate_yaml_document(source, Scenario)
    variant = scenario.model_copy(
        update={
            "harness": scenario.harness.model_copy(update={"shared_context": shared_context}),
            "oracle": scenario.oracle.model_copy(
                update={
                    "expected_origins": tuple(
                        expectation
                        for expectation in scenario.oracle.expected_origins
                        if shared_context
                        or not expectation.target.root.startswith("effect-selector:")
                    )
                }
            ),
        }
    )
    path = root / source
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(variant.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _outcome(cell: HiaaCell, result: ScenarioRunResult) -> MatrixRunOutcome:
    with SqliteEventStore(result.database_path) as store:
        effects = store.iter_run_effects(result.run_id)
    return MatrixRunOutcome(
        cell=cell,
        run_id=f"{result.scenario_id}-{cell.value}",
        effects=effects,
        receipts=result.receipts,
    )


def _selector(path: Path) -> EffectSelector:
    scenario = validate_yaml_document(path, Scenario)
    assert scenario.harm_selector is not None
    return next(
        item for item in scenario.effect_selectors if item.alias == scenario.harm_selector.alias
    )


def test_n0_neutralization_has_zero_causal_impact(tmp_path: Path) -> None:
    batch = _replay_runner().run(
        ROOT / "benign" / "n0_irrelevant_text.yaml",
        tmp_path / "n0-replay",
        seed="t12-n0",
    )

    assert len(batch.pairs) == 1
    report = batch.pairs[0].report
    assert report.ci == 0
    assert report.y_original is False
    assert report.y_neutral is False
    assert report.confirmed_influence_edges == ()


def test_c1_and_c2_each_form_a_complete_selector_bound_four_grid(
    tmp_path: Path,
) -> None:
    shutil.copytree(ROOT / "manifests", tmp_path / "scenarios" / "manifests")
    pairs = (
        (
            ROOT / "benign" / "n0_irrelevant_text.yaml",
            ROOT / "attacks" / "c1_context_composition.yaml",
        ),
        (
            ROOT / "benign" / "c2_tool_return_neutral.yaml",
            ROOT / "attacks" / "c2_tool_return_composition.yaml",
        ),
    )
    for index, (neutral, target) in enumerate(pairs):
        outcomes = []
        for cell, source, bridge in (
            (HiaaCell.P00, neutral, False),
            (HiaaCell.P01, neutral, True),
            (HiaaCell.P10, target, False),
            (HiaaCell.P11, target, True),
        ):
            path = _copy_variant(source, tmp_path, bridge)
            result = _runner().run(
                path,
                tmp_path / "runs" / f"grid-{index}-{cell.value}",
                seed=f"t12-grid-{index}",
            )
            outcomes.append(_outcome(cell, result))

        metrics = calculate_hiaa(_selector(target), tuple(outcomes))

        assert tuple(
            cell.outcomes for cell in (metrics.p00, metrics.p01, metrics.p10, metrics.p11)
        ) == ((False,), (False,), (False,), (True,))
        assert metrics.hiaa_run.value == 1.0
