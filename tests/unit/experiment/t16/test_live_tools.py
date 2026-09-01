import json

import pytest

from skillflow.experiment.t16.live_tools import (
    LiveToolRuntime,
    LiveToolSchemaError,
    UnknownEffectAliasError,
    live_tool_definitions,
)
from skillflow.experiment.t16.task_success_facts import payload_commitment_sha256


def _runtime() -> LiveToolRuntime:
    runtime = LiveToolRuntime(
        run_nonce="private-run-nonce",
        assets={"report": "approved report"},
        effect_alias_catalog={"operation-1": "context-harm"},
    )
    runtime.activate_effect_aliases(frozenset({"operation-1"}))
    return runtime


def test_safe_effect_creates_local_receipt_without_external_side_effect() -> None:
    runtime = _runtime()

    result = runtime.execute(
        "skillflow_safe_effect",
        '{"effect_alias":"operation-1","content":"fixed payload"}',
    )

    assert result.effect_alias == "context-harm"
    assert result.receipt_id is not None
    assert result.output == '{"executed":true,"sink":"local-receipt-only"}'
    assert runtime.effect_receipts == (result.receipt_id,)


def test_platform_hook_generates_run_session_bound_receipt_and_payload_commitment() -> None:
    runtime = LiveToolRuntime(
        run_nonce="private-run-nonce",
        assets={},
        effect_alias_catalog={"operation-1": "report-read"},
        platform_run_id="run-v3",
    )
    runtime.activate_session(0)
    runtime.activate_effect_aliases(frozenset({"operation-1"}))
    payload = b"safe-fixture:b0-report-read:v3"

    result = runtime.execute(
        "skillflow_safe_effect",
        json.dumps(
            {
                "effect_alias": "operation-1",
                "content": payload.decode("utf-8"),
            }
        ),
    )

    receipt = runtime.platform_receipts[0]
    assert result.receipt_id == receipt.receipt_id
    assert receipt.run_id == "run-v3"
    assert receipt.session_id == "session-0"
    assert receipt.effect_alias == "report-read"
    assert receipt.safe_sink_commitment_sha256 == payload_commitment_sha256(payload)
    assert payload.decode("utf-8") not in receipt.model_dump_json()


def test_model_cannot_submit_origin_ids_as_tool_provenance() -> None:
    runtime = _runtime()

    with pytest.raises(LiveToolSchemaError):
        runtime.execute(
            "skillflow_safe_effect",
            json.dumps(
                {
                    "effect_alias": "context-harm",
                    "content": "fixed payload",
                    "origin_ids": ["model-self-report"],
                }
            ),
        )

    assert runtime.effect_receipts == ()


def test_unknown_effect_alias_is_rejected_without_receipt() -> None:
    runtime = _runtime()

    with pytest.raises(UnknownEffectAliasError):
        runtime.execute(
            "skillflow_safe_effect",
            '{"effect_alias":"unregistered","content":"fixed payload"}',
        )

    assert runtime.effect_receipts == ()


def test_memory_and_assets_are_trial_local_and_strict() -> None:
    runtime = _runtime()

    read = runtime.execute("read_asset", '{"asset_id":"report"}')
    written = runtime.execute(
        "write_memory",
        '{"memory_key":"shared","content":"memory-target!"}',
    )
    recalled = runtime.execute("read_memory", '{"memory_key":"shared"}')

    assert read.output == '{"content":"approved report"}'
    assert written.output == '{"written":true}'
    assert recalled.output == '{"content":"memory-target!"}'
    assert (
        LiveToolRuntime(
            run_nonce="another-run",
            assets={"report": "approved report"},
            effect_alias_catalog={"operation-1": "context-harm"},
        ).memory_keys
        == ()
    )


def test_tool_schemas_never_expose_origin_ids() -> None:
    definitions = live_tool_definitions(
        ("read_asset", "write_memory", "read_memory", "skillflow_safe_effect")
    )

    assert len(definitions) == 4
    assert "origin_ids" not in json.dumps(definitions)
    assert "敏感" not in json.dumps(definitions, ensure_ascii=False)
    assert all(item["strict"] is True for item in definitions)


def test_session_effect_aliases_are_isolated_while_memory_stays_shared() -> None:
    runtime = LiveToolRuntime(
        run_nonce="m2-run",
        assets={},
        effect_alias_catalog={
            "operation-1": "residual-send-1",
            "operation-2": "residual-send-3",
        },
    )
    runtime.execute(
        "write_memory",
        '{"memory_key":"shared","content":"pending"}',
    )
    runtime.activate_effect_aliases(frozenset({"operation-1"}))

    with pytest.raises(UnknownEffectAliasError) as rejected:
        runtime.execute(
            "skillflow_safe_effect",
            '{"effect_alias":"operation-2","content":"fixed payload"}',
        )

    assert rejected.value.effect_alias == "residual-send-3"
    assert runtime.effect_receipts == ()
    accepted_one = runtime.execute(
        "skillflow_safe_effect",
        '{"effect_alias":"operation-1","content":"fixed payload"}',
    )
    assert accepted_one.effect_alias == "residual-send-1"

    runtime.activate_effect_aliases(frozenset({"operation-2"}))
    recalled = runtime.execute("read_memory", '{"memory_key":"shared"}')
    accepted_two = runtime.execute(
        "skillflow_safe_effect",
        '{"effect_alias":"operation-2","content":"fixed payload"}',
    )

    assert recalled.output == '{"content":"pending"}'
    assert accepted_two.effect_alias == "residual-send-3"
    assert len(runtime.effect_receipts) == 2
