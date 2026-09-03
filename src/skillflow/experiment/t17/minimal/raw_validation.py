"""从持久 Raw 读取强类型证据；不生成新的 Effect 或新 Receipt ID。"""

import json
from pathlib import Path
from typing import TypeVar

from pydantic import TypeAdapter

from skillflow.experiment.t17.minimal.schema_models import (
    schema_filename,
    static_model_validator,
    static_validator,
)
from skillflow.experiment.t17.minimal.task_evidence import TaskFacts, validate_effect_receipts
from skillflow.instrumentation.tool_receipt import ToolReceipt, ToolReceiptDraft, ToolReceiptIssuer
from skillflow.models.base import StrictModel
from skillflow.models.effects import EffectRecord
from skillflow.store.blob_store import RunBlobStore
from skillflow.store.event_store import EventStore

ModelT = TypeVar("ModelT", bound=StrictModel)
_RECEIPT_ADAPTER = TypeAdapter(ToolReceiptDraft)


def read_model(path: Path, model: type[ModelT]) -> ModelT:
    """同时执行模型与 Draft 2020-12 验证。"""
    payload = path.read_text(encoding="utf-8")
    static_model_validator(model).validate(json.loads(payload))
    return model.model_validate_json(payload)


def read_jsonl(path: Path, adapter: TypeAdapter[ModelT], schema_name: str) -> tuple[ModelT, ...]:
    """每一条原始 JSONL 记录均经模型和 Schema 复验。"""
    validator = static_validator(adapter.json_schema(), schema_filename(schema_name))
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        validator.validate(json.loads(line))
        record = adapter.validate_json(line)
        result.append(record)
    return tuple(result)


def restore_run_receipts(
    store: EventStore,
    root: Path,
    run_id: str,
) -> tuple[ToolReceipt, ...]:
    """只还原 EventStore 绑定且 Blob hash 已通过的原始 Runtime Receipt。"""
    effects = store.iter_run_effects(run_id)
    receipts = []
    with RunBlobStore(root, run_id) as blobs:
        for effect in effects:
            if not effect.executed:
                continue
            receipts.append(_restore_receipt(effect, store, blobs))
    result = tuple(receipts)
    validate_effect_receipts(
        TaskFacts(run_id, "raw-verification", {}, result, None), effects, store
    )
    return result


def verify_run_blobs(store: EventStore, root: Path, run_id: str) -> None:
    """内容只在内存校验，不写入公开报告。"""
    identifiers = {
        identifier
        for event in store.iter_run_events(run_id)
        for identifier in event.output_artifact_ids
    }
    with RunBlobStore(root, run_id) as blobs:
        for identifier in identifiers:
            artifact = store.get_artifact(identifier)
            reference = store.get_blob_ref(identifier)
            if artifact is None or reference is None:
                raise ValueError("minimal_runtime_artifact_blob_missing")
            if (
                reference.content_hash != artifact.content_hash
                or reference.content_length != artifact.content_length
            ):
                raise ValueError("minimal_artifact_blob_commitment_mismatch")
            blobs.get(reference)


def _restore_receipt(effect: EffectRecord, store: EventStore, blobs: RunBlobStore) -> ToolReceipt:
    event = None if effect.result_event_id is None else store.get_event(effect.result_event_id)
    if event is None or len(event.output_artifact_ids) != 1:
        raise ValueError("minimal_receipt_result_event_missing")
    artifact_id = event.output_artifact_ids[0]
    artifact = store.get_artifact(artifact_id)
    reference = store.get_blob_ref(artifact_id)
    if artifact is None or reference is None or artifact.created_by_event_id != event.event_id:
        raise ValueError("minimal_receipt_artifact_binding")
    payload = blobs.get(reference)
    static_validator(_RECEIPT_ADAPTER.json_schema(), schema_filename("tool-receipt")).validate(
        json.loads(payload)
    )
    draft = _RECEIPT_ADAPTER.validate_json(payload)
    if draft.receipt_artifact_id != artifact_id or draft.receipt_id != effect.tool_receipt_id:
        raise ValueError("minimal_receipt_id_binding")
    # 原 ID 与内容均来自已验证的 Runtime Blob；这里只还原对象，不签发新效果。
    receipt = ToolReceiptIssuer().issue(draft)
    if receipt.to_bytes() != payload:
        raise ValueError("minimal_receipt_canonical_bytes_mismatch")
    return receipt
