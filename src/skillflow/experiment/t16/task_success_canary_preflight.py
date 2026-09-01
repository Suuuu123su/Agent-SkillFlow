"""T16-D.2 v3.1 Canary 的 11 条调度与 0.25 美元授权边界。"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NoReturn

from skillflow.experiment.t16.task_success_live_preflight import (
    T16D2Environment,
    T16D2Inputs,
    load_t16d2r_inputs,
    select_canary_trials,
)
from skillflow.experiment.t16.task_success_matrix import TaskSuccessSmokeTrial

CANARY_MAX_TOTAL_USD = Decimal("0.25")
CANARY_PROVIDER = "openai"
CANARY_MODEL_ID = "gpt-5.6-luna"
T16E_MAX_TOTAL_USD = Decimal(1)
T16E_PROVIDER = "openai"
T16E_MODEL_ID = "gpt-5.5-2026-04-23"
CANARY_CONDITIONS = (
    "b0",
    "g0",
    "c1-p00",
    "c1-p01",
    "c1-p10",
    "c1-p11",
    "m2-control",
    "m2-target",
    "a1-claim",
    "a1-neutralized",
    "a2-structured-confirmation",
)


class T16D2CanaryEnvironmentError(ValueError):
    """Canary 的显式授权或冻结调度不一致。"""


@dataclass(frozen=True, slots=True)
class T16D2CanaryInputs:
    """经过成对与 HIAA selector 检查的 11 条 Canary。"""

    inputs: T16D2Inputs
    schedule: tuple[TaskSuccessSmokeTrial, ...]
    pairs_complete: bool
    c1_harm_selector_shared: bool


def load_t16d2r_canary_environment(environment: Mapping[str, str]) -> T16D2Environment:
    """解析不含秘密的 Canary 授权变量并拒绝预算扩张。"""
    required = (
        "SKILLFLOW_PROVIDER",
        "SKILLFLOW_MODEL_ID",
        "SKILLFLOW_MAX_USD",
        "SKILLFLOW_LIVE_APPROVED",
    )
    missing = tuple(name for name in required if not environment.get(name))
    if missing:
        _invalid(f"缺少 Canary 授权变量: {','.join(missing)}")
    try:
        budget = Decimal(environment["SKILLFLOW_MAX_USD"])
    except InvalidOperation as error:
        detail = "Canary 总预算不是有效金额"
        raise T16D2CanaryEnvironmentError(detail) from error
    if environment["SKILLFLOW_PROVIDER"] != CANARY_PROVIDER:
        _invalid("Canary Provider 必须为 openai")
    if environment["SKILLFLOW_MODEL_ID"] != CANARY_MODEL_ID:
        _invalid("Canary Model ID 必须为 gpt-5.6-luna")
    if budget != CANARY_MAX_TOTAL_USD:
        _invalid("Canary 总预算必须精确为 0.25 美元")
    if environment["SKILLFLOW_LIVE_APPROVED"] != "1":
        _invalid("Canary Live 未被显式授权")
    return T16D2Environment(
        provider=CANARY_PROVIDER,
        model_id=CANARY_MODEL_ID,
        max_total_usd=budget,
        live_approved=True,
    )


def load_t16e_environment(environment: Mapping[str, str]) -> T16D2Environment:
    """解析 T16-E 非秘密授权变量，拒绝 alias、替代模型或预算漂移。"""
    required = (
        "SKILLFLOW_SECOND_PROVIDER",
        "SKILLFLOW_SECOND_MODEL_ID",
        "SKILLFLOW_MAX_USD",
        "SKILLFLOW_LIVE_APPROVED",
    )
    missing = tuple(name for name in required if not environment.get(name))
    if missing:
        _invalid(f"缺少 T16-E 授权变量: {','.join(missing)}")
    try:
        budget = Decimal(environment["SKILLFLOW_MAX_USD"])
    except InvalidOperation as error:
        detail = "T16-E 总预算不是有效金额"
        raise T16D2CanaryEnvironmentError(detail) from error
    if environment["SKILLFLOW_SECOND_PROVIDER"] != T16E_PROVIDER:
        _invalid("T16-E Provider 必须精确为 openai")
    if environment["SKILLFLOW_SECOND_MODEL_ID"] != T16E_MODEL_ID:
        _invalid("T16-E Model ID 必须是用户选择的 GPT-5.5 固定快照")
    if budget != T16E_MAX_TOTAL_USD:
        _invalid("T16-E 总预算必须精确为 1 美元")
    if environment["SKILLFLOW_LIVE_APPROVED"] != "1":
        _invalid("T16-E Live 未被显式授权")
    return T16D2Environment(
        provider=T16E_PROVIDER,
        model_id=T16E_MODEL_ID,
        max_total_usd=budget,
        live_approved=True,
    )


def load_t16d2r_canary_inputs(root: Path) -> T16D2CanaryInputs:
    """加载 v3.1 冻结输入，并只保留预注册的 v01/r1 Canary。"""
    inputs = load_t16d2r_inputs(root)
    schedule = select_canary_trials(inputs.matrix)
    if tuple(item.condition_id for item in schedule) != CANARY_CONDITIONS:
        _invalid("Canary 条件或顺序发生变化")
    pairs_complete = _pairs_complete(schedule)
    selector_shared = _c1_selector_shared(schedule)
    if not pairs_complete:
        _invalid("Canary target/control pair_id 不完整")
    if not selector_shared:
        _invalid("Canary C1 四格未共享同一 harm_selector")
    return T16D2CanaryInputs(inputs, schedule, pairs_complete, selector_shared)


def _pairs_complete(schedule: tuple[TaskSuccessSmokeTrial, ...]) -> bool:
    by_condition = {item.condition_id: item.pair_id for item in schedule}
    return (
        by_condition["c1-p00"] == by_condition["c1-p10"]
        and by_condition["c1-p01"] == by_condition["c1-p11"]
        and by_condition["m2-control"] == by_condition["m2-target"]
        and by_condition["a1-claim"]
        == by_condition["a1-neutralized"]
        == by_condition["a2-structured-confirmation"]
    )


def _c1_selector_shared(schedule: tuple[TaskSuccessSmokeTrial, ...]) -> bool:
    selectors = {
        item.harm_selector.root
        for item in schedule
        if item.condition_id.startswith("c1-") and item.harm_selector is not None
    }
    return selectors == {"effect-selector:context-harm"}


def _invalid(detail: str) -> NoReturn:
    raise T16D2CanaryEnvironmentError(detail)
