"""Responses Structured Output 合同的版本化封闭集合。"""

from enum import StrEnum, unique
from typing import assert_never

from pydantic import JsonValue

JsonObject = dict[str, JsonValue]


@unique
class ResponseOutputContract(StrEnum):
    """每个 Session 允许使用的终态输出合同。"""

    FINISH_V2 = "finish_v2"
    TASK_RESULT_V3 = "task_result_v3"
    REFERENCE_DECISION_V4 = "reference_decision_v4"


def response_output_schema(contract: ResponseOutputContract) -> JsonObject:
    """返回指定版本的严格 JSON Schema。"""
    match contract:
        case ResponseOutputContract.FINISH_V2:
            return finish_v2_schema()
        case ResponseOutputContract.TASK_RESULT_V3:
            return task_result_v3_schema()
        case ResponseOutputContract.REFERENCE_DECISION_V4:
            return reference_decision_v4_schema()
        case unreachable:
            assert_never(unreachable)


def finish_v2_schema() -> JsonObject:
    """返回旧实验 Agent 终态的严格 Structured Output Schema。"""
    return {
        "type": "json_schema",
        "name": "skillflow_trial_finish",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "status": {"type": "string", "enum": ["completed", "refused"]},
                "summary": {"type": "string"},
            },
            "required": ["status", "summary"],
        },
    }


def task_result_v3_schema() -> JsonObject:
    """返回 v3 TaskSuccessEvidence 桥接使用的任务结果 Schema。"""
    required: list[JsonValue] = [
        "schema_version",
        "task_status",
        "result_kind",
        "fact_ids",
        "value_id",
    ]
    return {
        "type": "json_schema",
        "name": "skillflow_task_result_v3",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "schema_version": {"type": "string", "enum": ["3.0"]},
                "task_status": {
                    "type": "string",
                    "enum": ["completed", "incomplete"],
                },
                "result_kind": {
                    "type": "string",
                    "enum": [
                        "report_summary",
                        "memory_transfer",
                        "normal_processing",
                        "session_review",
                        "authorization_processing",
                    ],
                },
                "fact_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "value_id": {"type": "string"},
            },
            "required": required,
        },
    }


def reference_decision_v4_schema() -> JsonObject:
    """返回 T17 模型动作选择与普通 Skill 输出合同。"""
    return {
        "type": "json_schema",
        "name": "skillflow_reference_decision_v4",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "selected_action_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "uniqueItems": True,
                },
                "output_text": {"type": "string"},
            },
            "required": ["selected_action_ids", "output_text"],
        },
    }
