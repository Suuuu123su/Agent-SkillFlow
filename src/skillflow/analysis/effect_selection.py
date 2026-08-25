"""按 EffectSelector 选择具有真实 Tool Receipt 的已执行效果。"""

from dataclasses import dataclass

from skillflow.analysis.errors import AnalysisInvariantError
from skillflow.instrumentation.tool_receipt import ToolReceipt
from skillflow.models.effects import EffectRecord
from skillflow.models.scenario_parts import EffectSelector


@dataclass(frozen=True, slots=True)
class EffectSelectionFacts:
    """一个 Run 中待按同一 selector 核验的效果与 Receipt。"""

    effects: tuple[EffectRecord, ...]
    receipts: tuple[ToolReceipt, ...]
    selector: EffectSelector


@dataclass(frozen=True, slots=True)
class ReceiptedEffect:
    """一个 selector 命中且 Receipt 完整对齐的已执行效果。"""

    effect: EffectRecord
    receipt: ToolReceipt


def select_receipted_effects(
    facts: EffectSelectionFacts,
) -> tuple[ReceiptedEffect, ...]:
    """只返回匹配 selector、executed=true 且 Receipt 对齐的效果。"""
    receipts = _unique_receipts(facts.receipts)
    selected: list[ReceiptedEffect] = []
    for effect in facts.effects:
        if not effect.executed or not effect_matches_selector(effect, facts.selector):
            continue
        receipt_id = effect.tool_receipt_id
        receipt = None if receipt_id is None else receipts.get(receipt_id)
        if receipt is None or not _receipt_matches_effect(receipt, effect):
            raise AnalysisInvariantError(
                "select_receipted_effects",
                f"匹配且已执行的 Effect 缺少同 Run 真实 Receipt：{effect.effect_id}",
            )
        selected.append(ReceiptedEffect(effect, receipt))
    return tuple(selected)


def effect_matches_selector(effect: EffectRecord, selector: EffectSelector) -> bool:
    """按 action、精确 source 与精确 sink 匹配预注册 selector。"""
    actual_source = effect.effect.source
    expected_source = selector.source_pattern
    source_matches = (actual_source is None and expected_source is None) or (
        actual_source is not None
        and expected_source is not None
        and expected_source.matches_exact(actual_source)
    )
    return (
        source_matches
        and selector.action is effect.effect.action
        and selector.sink_pattern.matches_exact(effect.effect.sink)
    )


def _unique_receipts(receipts: tuple[ToolReceipt, ...]) -> dict[str, ToolReceipt]:
    unique: dict[str, ToolReceipt] = {}
    for receipt in receipts:
        previous = unique.get(receipt.receipt_id)
        if previous is not None and previous != receipt:
            raise AnalysisInvariantError(
                "select_receipted_effects",
                f"同一 receipt_id 出现冲突事实：{receipt.receipt_id}",
            )
        unique[receipt.receipt_id] = receipt
    return unique


def _receipt_matches_effect(receipt: ToolReceipt, effect: EffectRecord) -> bool:
    return (
        receipt.effect_id == effect.effect_id
        and receipt.request_event_id == effect.request_event_id
        and receipt.result_event_id == effect.result_event_id
        and receipt.decision_id == effect.decision_id
    )
