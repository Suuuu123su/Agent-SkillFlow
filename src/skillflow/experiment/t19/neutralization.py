"""只中和独立控制字段，保持任务事实；不匹配的输入明确失败。"""

import json


def neutralize_control(content: bytes) -> bytes:
    """接受冻结的 facts/control 合同，不可分离时不伪造净化成功。"""
    value = json.loads(content)
    if not isinstance(value, dict) or set(value) != {"facts", "control"}:
        raise ValueError("t19_neutralization_contract_missing")
    if not isinstance(value["control"], str) or not isinstance(value["facts"], dict):
        raise TypeError("t19_neutralization_not_separable")
    candidate = {**value, "control": " " * len(value["control"])}
    result = json.dumps(candidate, ensure_ascii=False, separators=(",", ":")).encode()
    if json.loads(result)["facts"] != value["facts"]:
        raise ValueError("t19_neutralization_changed_task_facts")
    if len(result) > len(content):
        raise ValueError("t19_neutralization_source_not_canonical")
    return result + b" " * (len(content) - len(result))
