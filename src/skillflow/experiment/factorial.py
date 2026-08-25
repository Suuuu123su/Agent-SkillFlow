"""单一 Harness feature 的二水平因子实验生成器。"""

from pathlib import Path
from typing import assert_never

from skillflow.experiment.inputs import (
    authorization_condition,
    scenario_reference,
    selected_harm_selector,
    slug,
)
from skillflow.experiment.matrix import (
    MatrixExecutionOutcome,
    MatrixExecutionRequest,
    execute_matrix,
)
from skillflow.models.execution import ExperimentKind
from skillflow.models.matrix import ExperimentMatrix, ExperimentVariant
from skillflow.models.matrix_design import HarnessFeature
from skillflow.models.references import ScenarioPath
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document


def execute_factorial(
    scenario_path: Path,
    feature: HarnessFeature,
    seeds: tuple[int, ...],
    output: Path | None,
) -> MatrixExecutionOutcome:
    """为每个 seed 机械生成 feature=off/on 两个核心 Run。"""
    scenario = validate_yaml_document(scenario_path, Scenario)
    unique_seeds = tuple(dict.fromkeys(seeds or (0,)))
    scenario_ref = scenario_reference(scenario_path)
    variants = tuple(
        _variant(scenario, scenario_ref, feature, seed, enabled)
        for seed in unique_seeds
        for enabled in (False, True)
    )
    matrix = ExperimentMatrix(
        schema_version="0.1",
        id=f"factorial-{slug(scenario.id)}-{feature.value}",
        variants=variants,
        determinism_repeats=1,
    )
    return execute_matrix(
        MatrixExecutionRequest(
            matrix_path=scenario_path,
            matrix=matrix,
            output=output,
            determinism_repeats=1,
            redacted=True,
            kind=ExperimentKind.FACTORIAL,
            source=scenario_ref.root,
        )
    )


def _variant(
    scenario: Scenario,
    scenario_ref: ScenarioPath,
    feature: HarnessFeature,
    seed: int,
    enabled: bool,
) -> ExperimentVariant:
    values = {
        "shared_context": scenario.harness.shared_context,
        "persistent_memory": scenario.harness.persistent_memory,
        "auto_approve_tools": scenario.harness.auto_approve_tools,
        "implicit_text_authorization": scenario.harness.implicit_text_authorization,
    }
    match feature:
        case HarnessFeature.SHARED_CONTEXT:
            values["shared_context"] = enabled
        case HarnessFeature.PERSISTENT_MEMORY:
            values["persistent_memory"] = enabled
        case HarnessFeature.AUTO_APPROVE_TOOLS:
            values["auto_approve_tools"] = enabled
        case HarnessFeature.IMPLICIT_TEXT_AUTHORIZATION:
            values["implicit_text_authorization"] = enabled
        case unreachable:
            assert_never(unreachable)
    level = "on" if enabled else "off"
    return ExperimentVariant(
        variant=f"{feature.value}-{level}-seed-{seed}",
        scenario=scenario_ref,
        seed=seed,
        target_skill_present=True,
        shared_context=values["shared_context"],
        persistent_memory=values["persistent_memory"],
        auto_approve_tools=values["auto_approve_tools"],
        enforcement_mode=scenario.execution.mode,
        provenance_mode=scenario.harness.provenance_mode,
        implicit_text_authorization=values["implicit_text_authorization"],
        harm_selector=(
            selected_harm_selector(scenario) if scenario.harm_selector is not None else None
        ),
        pair_id=None if scenario.pairing is None else scenario.pairing.pair_id,
        authorization_condition=authorization_condition(scenario),
    )
