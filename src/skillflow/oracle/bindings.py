"""Scripted action、Tool attempt 与 Receipt 的机械绑定。"""

from skillflow.oracle.effects import oracle_action_semantics
from skillflow.oracle.errors import OracleInvariantError
from skillflow.oracle.models import (
    OracleActionPlan,
    OracleAttemptEvidence,
    OracleInvocationEvidence,
    OracleReceiptEvidence,
)
from skillflow.oracle.state import OracleDataState


def bind_attempts(
    evidence: OracleInvocationEvidence,
    actions: dict[str, OracleActionPlan],
    state: OracleDataState,
) -> dict[str, OracleAttemptEvidence]:
    """验证每个声明动作恰好对应一个 Tool attempt，并记录 argument。"""
    attempts: dict[str, OracleAttemptEvidence] = {}
    for attempt in evidence.attempts:
        if attempt.action_id in attempts:
            raise OracleInvariantError(
                "attempt_binding",
                f"同一调用重复 action_id：{attempt.action_id}",
            )
        try:
            action = actions[attempt.action_id]
        except KeyError as error:
            raise OracleInvariantError(
                "attempt_binding",
                f"Tool attempt 引用了未声明动作：{attempt.action_id}",
            ) from error
        if (
            attempt.call_id != evidence.call_id
            or attempt.actor_id != evidence.skill_id
            or attempt.tool is not action.arguments.kind
        ):
            raise OracleInvariantError(
                "attempt_binding",
                f"Tool attempt 主体、call_id 或 Tool 不一致：{attempt.action_id}",
            )
        state.record_argument(
            evidence.skill_id,
            oracle_action_semantics(action.arguments),
            attempt,
        )
        attempts[attempt.action_id] = attempt
    if set(attempts) != set(actions):
        raise OracleInvariantError(
            "attempt_binding",
            "Scripted 动作与 Tool attempt 集合不一致",
        )
    return attempts


def bind_receipts(
    evidence: OracleInvocationEvidence,
    actions: dict[str, OracleActionPlan],
    attempts: dict[str, OracleAttemptEvidence],
) -> tuple[tuple[OracleActionPlan, OracleReceiptEvidence], ...]:
    """要求每个 executed attempt 恰好对应一个同 argument 的 Receipt。"""
    bound: list[tuple[OracleActionPlan, OracleReceiptEvidence]] = []
    seen: set[str] = set()
    for receipt in evidence.receipts:
        if receipt.action_id in seen:
            raise OracleInvariantError(
                "receipt_binding",
                f"同一调用重复 Receipt action_id：{receipt.action_id}",
            )
        seen.add(receipt.action_id)
        try:
            action = actions[receipt.action_id]
            attempt = attempts[receipt.action_id]
        except KeyError as error:
            raise OracleInvariantError(
                "receipt_binding",
                f"Receipt 缺少声明动作或 Tool attempt：{receipt.action_id}",
            ) from error
        if not attempt.executed or attempt.argument_artifact_id != receipt.argument_artifact_id:
            raise OracleInvariantError(
                "receipt_binding",
                f"Receipt 与 Tool attempt 不一致：{receipt.action_id}",
            )
        bound.append((action, receipt))
    executed = {attempt.action_id for attempt in evidence.attempts if attempt.executed}
    if seen != executed:
        raise OracleInvariantError(
            "receipt_binding",
            "已执行 Tool attempt 与 Receipt 集合不一致",
        )
    return tuple(bound)
