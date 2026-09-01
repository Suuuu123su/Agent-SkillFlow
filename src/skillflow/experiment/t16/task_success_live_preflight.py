"""T16-D.2 冻结输入、环境授权与 Canary 选择。"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NoReturn

from pydantic import BaseModel, ConfigDict

from skillflow.experiment.t16.preregistration import load_preregistration
from skillflow.experiment.t16.preregistration_models import T16Preregistration
from skillflow.experiment.t16.task_success_matrix import (
    TaskSuccessSmokeMatrix,
    TaskSuccessSmokeTrial,
)
from skillflow.experiment.t16.task_success_prereg_models import (
    TaskSuccessPreregistrationV3,
)
from skillflow.experiment.t16.task_success_registration import (
    load_task_success_preregistration,
    load_task_success_registry,
    load_task_success_smoke_matrix,
    validate_task_success_matrix,
)
from skillflow.experiment.t16.task_success_spec_models import (
    TaskSuccessSpecificationRegistry,
)

T16D2_MODEL_ID = "gpt-5.6-luna"
T16D2_PROVIDER = "openai"
T16D2_MAX_USD = Decimal(3)
EXPECTED_TRIAL_COUNT = 48
CANARY_CONDITION_ORDER = (
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


class T16D2Environment(BaseModel):
    """不含凭据的显式 Live 授权环境。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    model_id: str
    max_total_usd: Decimal
    live_approved: bool


class T16D2EnvironmentError(ValueError):
    """环境授权与冻结实验边界不一致。"""


@dataclass(frozen=True, slots=True)
class T16D2Inputs:
    """一次加载并完成交叉验证的全部冻结输入。"""

    root: Path
    parent_registration: T16Preregistration
    registration: TaskSuccessPreregistrationV3
    registry: TaskSuccessSpecificationRegistry
    matrix: TaskSuccessSmokeMatrix


def load_t16d2_environment(environment: Mapping[str, str]) -> T16D2Environment:
    """只读取四个非秘密授权变量并拒绝任何边界漂移。"""
    required = {
        "SKILLFLOW_PROVIDER",
        "SKILLFLOW_MODEL_ID",
        "SKILLFLOW_MAX_USD",
        "SKILLFLOW_LIVE_APPROVED",
    }
    missing = sorted(name for name in required if not environment.get(name))
    if missing:
        detail = f"缺少 T16-D.2 授权变量: {','.join(missing)}"
        raise T16D2EnvironmentError(detail)
    try:
        budget = Decimal(environment["SKILLFLOW_MAX_USD"])
    except InvalidOperation as error:
        detail = "SKILLFLOW_MAX_USD 不是有效金额"
        raise T16D2EnvironmentError(detail) from error
    if environment["SKILLFLOW_PROVIDER"] != T16D2_PROVIDER:
        _invalid("Provider 与冻结配置不一致")
    if environment["SKILLFLOW_MODEL_ID"] != T16D2_MODEL_ID:
        _invalid("Model ID 与冻结配置不一致")
    if budget != T16D2_MAX_USD:
        _invalid("总预算必须精确为 3 美元")
    if environment["SKILLFLOW_LIVE_APPROVED"] != "1":
        _invalid("Live 未被显式授权")
    return T16D2Environment(
        provider=T16D2_PROVIDER,
        model_id=T16D2_MODEL_ID,
        max_total_usd=budget,
        live_approved=True,
    )


def load_t16d2_inputs(root: Path) -> T16D2Inputs:
    """读取并交叉验证 v2 父合同与 v3 三份冻结输入。"""
    t16 = root / "experiments" / "t16"
    parent = load_preregistration(t16 / "preregistration_t16c_v2.yaml")
    registration = load_task_success_preregistration(t16 / "preregistration_task_success_v3.yaml")
    registry = load_task_success_registry(t16 / "task_success_assertions_v3.yaml")
    matrix = load_task_success_smoke_matrix(t16 / "matrix_task_success_smoke_v3.yaml")
    validate_task_success_matrix(matrix, registration, registry)
    if registration.parent_preregistration_id != parent.id:
        _invalid("v3 preregistration 未绑定冻结的 v2 父合同")
    if len(matrix.trials) != EXPECTED_TRIAL_COUNT:
        _invalid("v3 Matrix 必须恰好包含 48 条 Trial")
    return T16D2Inputs(root, parent, registration, registry, matrix)


def load_t16d2r_inputs(root: Path) -> T16D2Inputs:
    """加载 v3.1 修订，同时复用并验证字节不变的 v3 Matrix 与研究合同。"""
    baseline = load_t16d2_inputs(root)
    revised = load_task_success_preregistration(
        root / "experiments" / "t16" / "preregistration_task_success_v3_1.yaml"
    )
    expected = baseline.registration.model_dump(mode="json")
    expected.update(
        schema_version="0.3.1",
        protocol_version="3.1",
        id="t16-task-success-bridge-preregistration-v3.1",
    )
    expected_budget = dict(expected["budget"])
    expected_budget["max_agent_turns"] = 16
    expected["budget"] = expected_budget
    if revised.model_dump(mode="json") != expected:
        _invalid("v3.1 除版本身份与 16-step 上限外不得改变任何冻结因素")
    return T16D2Inputs(
        baseline.root,
        baseline.parent_registration,
        revised,
        baseline.registry,
        baseline.matrix,
    )


def select_canary_trials(
    matrix: TaskSuccessSmokeMatrix,
) -> tuple[TaskSuccessSmokeTrial, ...]:
    """按冻结顺序选首个 v01/r1 完整配对 Canary。"""
    selected: list[TaskSuccessSmokeTrial] = []
    for condition_id in CANARY_CONDITION_ORDER:
        match = next(
            (
                item
                for item in matrix.trials
                if item.condition_id == condition_id
                and item.semantic_instance_id.endswith("v01")
                and item.repeat_index == 1
            ),
            None,
        )
        if match is None:
            detail = f"Canary 条件不完整: {condition_id}"
            raise T16D2EnvironmentError(detail)
        selected.append(match)
    return tuple(selected)


def _invalid(detail: str) -> NoReturn:
    raise T16D2EnvironmentError(detail)
