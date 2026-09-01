"""LiveTrialRecord 的版本化 JSON Schema 条件。"""

from pydantic import JsonValue

LIVE_TRIAL_SCHEMA_EXTRA: dict[str, JsonValue] = {
    "allOf": [
        {
            "if": {
                "properties": {"schema_version": {"const": "0.3"}},
                "required": ["schema_version"],
            },
            "then": {
                "required": [
                    "run_id",
                    "phase_contract_sha256",
                    "task_success_evidence",
                    "task_success_result",
                ],
                "properties": {
                    "run_id": {"type": "string", "minLength": 1},
                    "phase_contract_sha256": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                    },
                    "task_success_evidence": {"minItems": 1},
                    "task_success_result": {"not": {"type": "null"}},
                },
            },
        },
        {
            "if": {
                "properties": {"schema_version": {"enum": ["0.1", "0.2"]}},
                "required": ["schema_version"],
            },
            "then": {
                "properties": {
                    "run_id": {"type": "null"},
                    "task_success_evidence": {"maxItems": 0},
                    "task_success_result": {"type": "null"},
                }
            },
        },
        {
            "if": {
                "properties": {"schema_version": {"const": "0.2"}},
                "required": ["schema_version"],
            },
            "then": {
                "required": ["phase_contract_sha256"],
                "properties": {
                    "phase_contract_sha256": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                    }
                },
            },
        },
    ]
}
