"""T12 任务成功断言的纯机械求值。"""

from dataclasses import dataclass
from typing import assert_never

from skillflow.analysis.effect_selection import (
    EffectSelectionFacts,
    select_receipted_effects,
)
from skillflow.instrumentation.tool_receipt import ToolReceipt
from skillflow.models.effects import EffectRecord
from skillflow.models.provenance import Artifact
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_research import (
    ArtifactSha256Assertion,
    EffectReceiptedAssertion,
)


@dataclass(frozen=True, slots=True)
class TaskSuccessFacts:
    """成功判据所需的固定 Scenario 与已记录运行事实。"""

    scenario: Scenario
    artifact_ids_by_alias: dict[str, str]
    artifacts: tuple[Artifact, ...]
    effects: tuple[EffectRecord, ...]
    receipts: tuple[ToolReceipt, ...]


def evaluate_task_success(facts: TaskSuccessFacts) -> bool | None:
    """逐条求值并取合取；未声明断言时返回 N/A。"""
    if not facts.scenario.success_assertions:
        return None
    artifacts = {artifact.artifact_id: artifact for artifact in facts.artifacts}
    selectors = {selector.alias: selector for selector in facts.scenario.effect_selectors}
    results: list[bool] = []
    for assertion in facts.scenario.success_assertions:
        match assertion:
            case ArtifactSha256Assertion(target=target, expected_sha256=expected):
                artifact_id = facts.artifact_ids_by_alias.get(target.alias)
                artifact = None if artifact_id is None else artifacts.get(artifact_id)
                results.append(artifact is not None and artifact.content_hash == expected)
            case EffectReceiptedAssertion(target=target, expected=expected):
                selected = select_receipted_effects(
                    EffectSelectionFacts(
                        effects=facts.effects,
                        receipts=facts.receipts,
                        selector=selectors[target.alias],
                    )
                )
                results.append(bool(selected) is expected)
            case unreachable:
                assert_never(unreachable)
    return all(results)
