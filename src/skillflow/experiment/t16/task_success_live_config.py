"""T16-D.2 对 v2 Live 配置与 v3 冻结预算取严格交集。"""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from skillflow.experiment.t16.live_config import (
    T16CLiveConfig,
    T16ELiveConfig,
    load_t16c_config,
    load_t16e_config,
)
from skillflow.experiment.t16.task_success_registration import (
    load_task_success_preregistration,
)

MODEL_ID_MISMATCH = "v3 与 T16-C Provider Model ID 不一致"
TEMPERATURE_MISMATCH = "v3 与 T16-C temperature 不一致"
REASONING_MISMATCH = "v3 与 T16-C reasoning effort 不一致"
T16D2R_PROTOCOL_ID = "t16-task-success-bridge-preregistration-v3.1"
T16D2R_CONFIG_ID = "t16d2r-v3.1-gpt-5.6-luna"
T16D2R_CANARY_CONFIG_ID = "t16d2r-v3.1-canary-gpt-5.6-luna"
T16D2R_PROTOCOL_SHA256 = "9ad38f19e1e9ba87d6c863c988af14b4a6e145338a2f9a79ee4a0b2a489deca4"
T16D2R_CONFIG_SHA256 = "6eedc1313c8ed84d39a7e5788746912ea36dac94c22f29f3331851a6e6c3fe56"
T16D2R_CANARY_CONFIG_SHA256 = "0ab28b3f0907a6cfcf6a126af67f23ed9a6f646d00baea02cc16c548fcd20ba2"
T16D2R_CANARY_TOTAL_USD = Decimal("0.25")
T16E_CONFIG_SHA256 = "e97aadc7bf5135f57ac64ad9e05e9726e12087f087618a577974e08febebe9ae"


def build_t16d2_live_config(root: Path) -> T16CLiveConfig:
    """沿用已验证 Provider/价格，只收紧为 v3 预算上限。"""
    t16 = root / "experiments" / "t16"
    parent = load_t16c_config(t16 / "t16c_live.yaml")
    registration = load_task_success_preregistration(t16 / "preregistration_task_success_v3.yaml")
    if registration.provider.model_id != parent.provider.model_id:
        raise ValueError(MODEL_ID_MISMATCH)
    if registration.provider.temperature != parent.provider.temperature:
        raise ValueError(TEMPERATURE_MISMATCH)
    if registration.provider.reasoning_effort != parent.provider.reasoning_effort:
        raise ValueError(REASONING_MISMATCH)
    frozen = registration.budget
    budget = parent.budget.model_copy(
        update={
            "allow_live": True,
            "max_total_usd": frozen.max_total_usd,
            "max_cost_per_run_usd": min(
                parent.budget.max_cost_per_run_usd,
                frozen.max_cost_per_run_usd,
            ),
            "max_agent_turns": min(
                parent.budget.max_agent_turns,
                frozen.max_agent_turns,
            ),
            "max_output_tokens_per_turn": min(
                parent.budget.max_output_tokens_per_turn,
                frozen.max_output_tokens_per_turn,
            ),
            "max_retries": min(parent.budget.max_retries, frozen.max_retries),
        }
    )
    return T16CLiveConfig.model_validate(
        parent.model_copy(
            update={
                "id": "t16d2-v3-gpt-5.6-luna",
                "budget": budget,
            }
        ).model_dump(mode="python")
    )


def _config_sha256(config: T16CLiveConfig) -> str:
    encoded = json.dumps(
        config.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_t16d2r_live_config(root: Path) -> T16CLiveConfig:
    """构造 v3.1 新 Attempt 配置；只把冻结 Agent Step 上限改为 16。"""
    t16 = root / "experiments" / "t16"
    preregistration_path = t16 / "preregistration_task_success_v3_1.yaml"
    if hashlib.sha256(preregistration_path.read_bytes()).hexdigest() != T16D2R_PROTOCOL_SHA256:
        detail = "v3.1 protocol SHA-256 不一致"
        raise ValueError(detail)
    parent = load_t16c_config(t16 / "t16c_live.yaml")
    registration = load_task_success_preregistration(preregistration_path)
    if registration.id != T16D2R_PROTOCOL_ID:
        detail = "v3.1 protocol ID 不一致"
        raise ValueError(detail)
    if registration.provider.model_id != parent.provider.model_id:
        raise ValueError(MODEL_ID_MISMATCH)
    if registration.provider.temperature != parent.provider.temperature:
        raise ValueError(TEMPERATURE_MISMATCH)
    if registration.provider.reasoning_effort != parent.provider.reasoning_effort:
        raise ValueError(REASONING_MISMATCH)
    frozen = registration.budget
    budget = parent.budget.model_copy(
        update={
            "allow_live": True,
            "max_total_usd": frozen.max_total_usd,
            "max_cost_per_run_usd": min(
                parent.budget.max_cost_per_run_usd,
                frozen.max_cost_per_run_usd,
            ),
            # v3.1 正是对旧 8-step 子协议的显式修订；不继承 T16-C 的旧 12-step 值。
            "max_agent_turns": frozen.max_agent_turns,
            "max_output_tokens_per_turn": min(
                parent.budget.max_output_tokens_per_turn,
                frozen.max_output_tokens_per_turn,
            ),
            "max_retries": min(parent.budget.max_retries, frozen.max_retries),
        }
    )
    config = T16CLiveConfig.model_validate(
        parent.model_copy(
            update={
                "schema_version": "0.2",
                "id": T16D2R_CONFIG_ID,
                "budget": budget,
            }
        ).model_dump(mode="python")
    )
    if _config_sha256(config) != T16D2R_CONFIG_SHA256:
        detail = "v3.1 live config SHA-256 不一致"
        raise ValueError(detail)
    return config


def build_t16d2r_canary_config(root: Path) -> T16CLiveConfig:
    """把已冻结 v3.1 执行合同收紧到用户批准的 11 条阶段预算。"""
    base = build_t16d2r_live_config(root)
    budget = base.budget.model_copy(update={"max_total_usd": T16D2R_CANARY_TOTAL_USD})
    config = T16CLiveConfig.model_validate(
        base.model_copy(
            update={
                "id": T16D2R_CANARY_CONFIG_ID,
                "budget": budget,
                "smoke_max_total_usd": T16D2R_CANARY_TOTAL_USD,
            }
        ).model_dump(mode="python")
    )
    if _config_sha256(config) != T16D2R_CANARY_CONFIG_SHA256:
        detail = "v3.1 Canary live config SHA-256 不一致"
        raise ValueError(detail)
    return config


def build_t16e_canary_config(root: Path) -> T16ELiveConfig:
    """加载并复核用户明确选择的 GPT-5.5 固定快照配置。"""
    config = load_t16e_config(root / "experiments" / "t16" / "t16e_second_model.yaml")
    registration = load_task_success_preregistration(
        root / "experiments" / "t16" / "preregistration_task_success_v3_1.yaml"
    )
    if config.provider.reasoning_effort != registration.provider.reasoning_effort:
        raise ValueError(REASONING_MISMATCH)
    if config.provider.temperature != registration.provider.temperature:
        raise ValueError(TEMPERATURE_MISMATCH)
    if config.budget.max_agent_turns != registration.budget.max_agent_turns:
        detail = "T16-E Agent Step 与 v3.1 不一致"
        raise ValueError(detail)
    if _config_sha256(config) != T16E_CONFIG_SHA256:
        detail = "T16-E config SHA-256 不一致"
        raise ValueError(detail)
    return config
