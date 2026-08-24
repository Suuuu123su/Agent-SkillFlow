"""只能由 Mock Tool Adapter 签发的强类型 Receipt。"""

import json
from dataclasses import dataclass
from datetime import datetime

from skillflow.instrumentation.errors import ReceiptAuthorityError
from skillflow.instrumentation.tool_types import MockToolName


@dataclass(frozen=True, slots=True)
class ToolReceiptDraft:
    """Mock Tool Adapter 内部使用的 Receipt 数据。"""

    receipt_id: str
    tool: MockToolName
    effect_id: str
    request_event_id: str
    result_event_id: str
    decision_id: str
    actor_id: str
    call_id: str
    action_id: str
    argument_artifact_id: str
    receipt_artifact_id: str
    timestamp: datetime
    output_artifact_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, init=False)
class ToolReceipt:
    """Mock Effect 已执行的强类型证据。"""

    receipt_id: str
    tool: MockToolName
    effect_id: str
    request_event_id: str
    result_event_id: str
    decision_id: str
    actor_id: str
    call_id: str
    action_id: str
    argument_artifact_id: str
    receipt_artifact_id: str
    timestamp: datetime
    output_artifact_ids: tuple[str, ...]

    def __init__(self) -> None:
        """拒绝普通调用方直接构造。"""
        raise ReceiptAuthorityError

    def to_bytes(self) -> bytes:
        """输出不含 Tool 参数明文的规范 JSON。"""
        return json.dumps(
            {
                "action_id": self.action_id,
                "actor_id": self.actor_id,
                "argument_artifact_id": self.argument_artifact_id,
                "call_id": self.call_id,
                "decision_id": self.decision_id,
                "effect_id": self.effect_id,
                "output_artifact_ids": self.output_artifact_ids,
                "receipt_id": self.receipt_id,
                "receipt_artifact_id": self.receipt_artifact_id,
                "request_event_id": self.request_event_id,
                "result_event_id": self.result_event_id,
                "timestamp": self.timestamp.isoformat(),
                "tool": self.tool.value,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()


class ToolReceiptIssuer:
    """仅由 MockToolAdapter 持有的 API 级签发能力。"""

    def issue(self, draft: ToolReceiptDraft) -> ToolReceipt:
        """从已执行的 Mock Effect 创建不可变 Receipt。"""
        receipt = object.__new__(ToolReceipt)
        object.__setattr__(receipt, "receipt_id", draft.receipt_id)
        object.__setattr__(receipt, "tool", draft.tool)
        object.__setattr__(receipt, "effect_id", draft.effect_id)
        object.__setattr__(receipt, "request_event_id", draft.request_event_id)
        object.__setattr__(receipt, "result_event_id", draft.result_event_id)
        object.__setattr__(receipt, "decision_id", draft.decision_id)
        object.__setattr__(receipt, "actor_id", draft.actor_id)
        object.__setattr__(receipt, "call_id", draft.call_id)
        object.__setattr__(receipt, "action_id", draft.action_id)
        object.__setattr__(receipt, "argument_artifact_id", draft.argument_artifact_id)
        object.__setattr__(receipt, "receipt_artifact_id", draft.receipt_artifact_id)
        object.__setattr__(receipt, "timestamp", draft.timestamp)
        object.__setattr__(receipt, "output_artifact_ids", draft.output_artifact_ids)
        return receipt
