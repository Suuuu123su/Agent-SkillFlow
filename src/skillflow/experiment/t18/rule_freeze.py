"""留出技能构造前固定实际路由源码，不借助运行结果修改规则。"""

import hashlib
import json
from pathlib import Path
from typing import Literal

from skillflow.defense.router import ROUTER_VERSION
from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.models.base import NonEmptyStr, StrictModel

SOURCES = tuple(
    "src/skillflow/defense/" + name + ".py"
    for name in (
        "models",
        "router",
        "task_plan",
        "gates",
        "memory",
        "signals",
    )
)
FREEZE_PATH = "experiments/t18/router-rule-freeze.json"


class RuleFreeze(StrictModel):
    """留出构造前的路由规则源码清单。"""

    schema_version: Literal["18.0"] = "18.0"
    version: NonEmptyStr
    rule_sources: dict[NonEmptyStr, Sha256]
    created_before_held_out_catalog: Literal[True] = True
    paid_api_calls: Literal[0] = 0


def current_rules(root: Path) -> RuleFreeze:
    """读取当前六个规则文件，不扫描历史数据。"""
    return RuleFreeze(
        version=ROUTER_VERSION,
        rule_sources={p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in SOURCES},
    )


def freeze_rules(root: Path) -> RuleFreeze:
    """首次生成仅新增文件；存在时只验证，不覆盖。"""
    path = root / FREEZE_PATH
    current = current_rules(root)
    if path.exists():
        return verify_rules(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                current.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2
            )
            + "\n"
        )
    return current


def verify_rules(root: Path) -> RuleFreeze:
    """规则冻结后，任何字节变化都必须明确处理。"""
    expected = RuleFreeze.model_validate_json((root / FREEZE_PATH).read_text(encoding="utf-8"))
    if expected != current_rules(root):
        raise ValueError("t18_router_rules_changed_after_freeze")
    return expected
