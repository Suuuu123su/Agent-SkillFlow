"""T16-D.2 冻结输入与旧 v2 证据的不可变复核。"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from skillflow.experiment.t16.live_config import T16CLiveConfig
from skillflow.experiment.t16.task_success_live_models import T16D2PreflightManifest
from skillflow.experiment.t16.task_success_live_preflight import T16D2Inputs

V2_FROZEN_FILES = {
    "v2_preregistration": (
        "experiments/t16/preregistration_t16c_v2.yaml",
        "f12f6fe08e0055ebf749f16adc4c104f8cb8271bf3c7cf8202f1c01767a5b907",
    ),
    "v2_smoke_matrix": (
        "experiments/t16/matrix_smoke_t16c_v2.yaml",
        "e876392a07186f0c989ecfc1911a5f03a4fef11f48a8c37a1e5c76e7a1da0731",
    ),
    "v2_model1_matrix": (
        "experiments/t16/matrix_model1_t16c_v2.yaml",
        "7efbcc31dc0d6792a80894e794b787bccd6f52de82df0c6c7e51fff276adb0b3",
    ),
    "v2_model2_subset_matrix": (
        "experiments/t16/matrix_model2_subset_t16c_v2.yaml",
        "302e171b4fad25b79cda6f78119d4de23270904536e998e82e6e97e74d5072f6",
    ),
    "v2_smoke_jsonl": (
        "runs/t16c-v2-live-20260829-01/attempt-01/smoke/trial-results.jsonl",
        "89dcbc44ca4084ee41645f189df471353fbbbd99a7365c6346e8d99c058d6738",
    ),
    "v2_model1_jsonl": (
        "runs/t16c-v2-live-20260829-01/attempt-01/model1/trial-results.jsonl",
        "2538b342bff20799964392eac15f545c47e10f6f55e4c56c315b1a85d3618f04",
    ),
    "v2_reanalysis_v04": (
        "runs/t16c-v2-live-20260829-01/attempt-01/model1/metrics-reanalysis-v0.4.json",
        "325c2ab7231f0773a99f1ac55c8a087e07aa92259b72ed70a0a5e63ae2f24c8a",
    ),
}
EXPECTED_TRIAL_COUNT = 48
MATRIX_IDENTITY_INVALID = "v3 Matrix Trial 数量或唯一性错误"
PAIRING_INVALID = "v3 Matrix 配对或 C1 四格不完整"
CanonicalValue = TypeVar("CanonicalValue")


class T16D2PreflightError(RuntimeError):
    """任何冻结输入漂移都必须发生在首次 API 调用之前。"""


def build_t16d2_preflight_manifest(
    inputs: T16D2Inputs,
    created_at: datetime,
) -> T16D2PreflightManifest:
    """复核 48 条 Matrix、配对和旧证据，并冻结当前执行代码。"""
    root = inputs.root
    v2_hashes: dict[str, str] = {}
    for name, (relative, expected) in V2_FROZEN_FILES.items():
        actual = sha256_file(root / relative)
        if actual != expected:
            detail = f"冻结 v2 证据漂移: {name}"
            raise T16D2PreflightError(detail)
        v2_hashes[name] = actual
    trial_ids = tuple(item.trial_id for item in inputs.matrix.trials)
    if len(trial_ids) != EXPECTED_TRIAL_COUNT or len(set(trial_ids)) != EXPECTED_TRIAL_COUNT:
        raise T16D2PreflightError(MATRIX_IDENTITY_INVALID)
    _require_pair_completeness(inputs)
    t16 = root / "experiments" / "t16"
    matrix_sha = sha256_file(t16 / "matrix_task_success_smoke_v3.yaml")
    prereg_sha = sha256_file(t16 / "preregistration_task_success_v3.yaml")
    spec_sha = sha256_file(t16 / "task_success_assertions_v3.yaml")
    prompt_sha = canonical_sha256(inputs.registration.prompt_contract.model_dump(mode="json"))
    source_hashes = _source_hashes(root)
    phase_payload = {
        "matrix_sha256": matrix_sha,
        "preregistration_sha256": prereg_sha,
        "task_success_specification_sha256": spec_sha,
        "prompt_contract_sha256": prompt_sha,
        "v2_frozen_hashes": v2_hashes,
        "source_hashes": source_hashes,
        "provider": "openai",
        "model_id": "gpt-5.6-luna",
        "max_total_usd": "3",
    }
    return T16D2PreflightManifest(
        created_at=created_at,
        matrix_sha256=matrix_sha,
        preregistration_sha256=prereg_sha,
        task_success_specification_sha256=spec_sha,
        prompt_contract_sha256=prompt_sha,
        phase_contract_sha256=canonical_sha256(phase_payload),
        v2_frozen_hashes=v2_hashes,
        source_hashes=source_hashes,
    )


def build_t16d2r_preflight_manifest(
    inputs: T16D2Inputs,
    config: T16CLiveConfig,
    created_at: datetime,
) -> T16D2PreflightManifest:
    """为不可与 v3 合并的新 v3.1 Attempt 构造独立阶段合同。"""
    root = inputs.root
    v2_hashes: dict[str, str] = {}
    for name, (relative, expected) in V2_FROZEN_FILES.items():
        actual = sha256_file(root / relative)
        if actual != expected:
            detail = f"冻结 v2 证据漂移: {name}"
            raise T16D2PreflightError(detail)
        v2_hashes[name] = actual
    trial_ids = tuple(item.trial_id for item in inputs.matrix.trials)
    if len(trial_ids) != EXPECTED_TRIAL_COUNT or len(set(trial_ids)) != EXPECTED_TRIAL_COUNT:
        raise T16D2PreflightError(MATRIX_IDENTITY_INVALID)
    _require_pair_completeness(inputs)
    t16 = root / "experiments" / "t16"
    matrix_sha = sha256_file(t16 / "matrix_task_success_smoke_v3.yaml")
    prereg_sha = sha256_file(t16 / "preregistration_task_success_v3_1.yaml")
    spec_sha = sha256_file(t16 / "task_success_assertions_v3.yaml")
    prompt_sha = canonical_sha256(inputs.registration.prompt_contract.model_dump(mode="json"))
    source_hashes = _source_hashes(root)
    phase_payload = {
        "protocol_id": inputs.registration.id,
        "protocol_version": inputs.registration.protocol_version,
        "live_config": config.model_dump(mode="json"),
        "matrix_sha256": matrix_sha,
        "preregistration_sha256": prereg_sha,
        "task_success_specification_sha256": spec_sha,
        "prompt_contract_sha256": prompt_sha,
        "v2_frozen_hashes": v2_hashes,
        "source_hashes": source_hashes,
        "provider": config.provider.kind.value,
        "model_id": config.provider.model_id,
        "max_total_usd": str(config.budget.max_total_usd),
    }
    return T16D2PreflightManifest(
        created_at=created_at,
        matrix_sha256=matrix_sha,
        preregistration_sha256=prereg_sha,
        task_success_specification_sha256=spec_sha,
        prompt_contract_sha256=prompt_sha,
        phase_contract_sha256=canonical_sha256(phase_payload),
        v2_frozen_hashes=v2_hashes,
        source_hashes=source_hashes,
    )


def sha256_file(path: Path) -> str:
    """流式计算文件 SHA-256。"""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        detail = f"无法读取冻结文件: {path}"
        raise T16D2PreflightError(detail) from error
    return digest.hexdigest()


def canonical_sha256(value: CanonicalValue) -> str:
    """对结构化合同使用固定 JSON 编码。"""
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_hashes(root: Path) -> dict[str, str]:
    files = sorted((root / "src" / "skillflow" / "experiment" / "t16").glob("*.py"))
    schema_files = sorted((root / "schemas").glob("t16*.json"))
    return {
        path.relative_to(root).as_posix(): sha256_file(path) for path in (*files, *schema_files)
    }


def _require_pair_completeness(inputs: T16D2Inputs) -> None:
    by_identity: dict[tuple[str, int], set[str]] = {}
    for trial in inputs.matrix.trials:
        template = trial.semantic_instance_id.rsplit("-", 1)[-1]
        by_identity.setdefault((template, trial.repeat_index), set()).add(trial.condition_id)
    required = {
        "c1-p00",
        "c1-p01",
        "c1-p10",
        "c1-p11",
        "m2-control",
        "m2-target",
        "a1-claim",
        "a1-neutralized",
        "a2-structured-confirmation",
    }
    if any(not required.issubset(conditions) for conditions in by_identity.values()):
        raise T16D2PreflightError(PAIRING_INVALID)
