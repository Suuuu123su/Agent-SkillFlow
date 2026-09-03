"""最小输入、Phase Contract 与 Raw 哈希的不可覆盖写入。"""

import hashlib
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from skillflow.experiment.io import write_json_model
from skillflow.experiment.t17.minimal.configuration import build_minimal_configuration
from skillflow.experiment.t17.minimal.contracts import MinimalConfiguration
from skillflow.experiment.t17.minimal.run_models import (
    FileDigest,
    MinimalDomain,
    MinimalPhaseContract,
    RawManifest,
)
from skillflow.models.base import StrictModel
from skillflow.validation import validate_yaml_document


def model_digest(model: StrictModel) -> str:
    """确定性结构哈希，与漂亮打印格式无关。"""
    payload = json.dumps(
        model.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def write_checked_json(path: Path, model: StrictModel) -> None:
    """每个新文件写入前复验完整 JSON Schema。"""
    Draft202012Validator(type(model).model_json_schema()).validate(model.model_dump(mode="json"))
    write_json_model(path, model)


def freeze_minimal_configuration(project_root: Path, destination: Path) -> Path:
    """由类型模型机械生成全新 YAML，不覆盖已冻结的输入。"""
    configuration = build_minimal_configuration(project_root)
    destination.mkdir(parents=True, exist_ok=False)
    for name, model in (
        ("preregistration.yaml", configuration),
        ("matrix.yaml", configuration.matrix),
    ):
        with (destination / name).open("x", encoding="utf-8", newline="\n") as stream:
            yaml.safe_dump(
                model.model_dump(mode="json"), stream, allow_unicode=True, sort_keys=True
            )
    return destination / "preregistration.yaml"


def validate_configuration(path: Path, project_root: Path) -> MinimalConfiguration:
    """字节哈希和完整模型同时一致才允许新的离线 Run。"""
    configuration = validate_yaml_document(path, MinimalConfiguration)
    if configuration != build_minimal_configuration(project_root):
        raise ValueError("minimal_configuration_contract_drift")
    for reference, expected in configuration.source_sha256.items():
        if file_digest(resolve_relative(project_root, reference)) != expected:
            raise ValueError("minimal_configuration_source_hash_mismatch")
    return configuration


def freeze_phase(
    configuration_path: Path,
    project_root: Path,
    domain: MinimalDomain,
) -> MinimalPhaseContract:
    """冻结实际被用到的 Runtime 代码，而非无关的未跟踪草稿。"""
    package = project_root / "src" / "skillflow"
    # protocol.py 是本轮开始前已有、未导入的用户草稿，不属于本次交付。
    draft = package / "experiment" / "t17" / "protocol.py"
    sources = {path for path in package.rglob("*.py") if path != draft}
    sources.update((project_root / "schemas").glob("*.json"))
    hashes = {
        path.relative_to(project_root).as_posix(): file_digest(path) for path in sorted(sources)
    }
    return MinimalPhaseContract(
        domain=domain,
        configuration_sha256=file_digest(configuration_path),
        matrix_sha256=file_digest(configuration_path.with_name("matrix.yaml")),
        runtime_source_sha256=hashes,
    )


def build_raw_manifest(root: Path, phase: MinimalPhaseContract) -> RawManifest:
    """为已关闭的 Runtime 目录登记全部 Raw，不删除或改写原文件。"""
    values = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        payload = path.read_bytes()
        values.append(
            FileDigest(
                path=path.relative_to(root).as_posix(),
                sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
                jsonl_records=len(payload.splitlines()) if path.suffix == ".jsonl" else None,
            )
        )
    return RawManifest(
        domain=phase.domain, phase_contract_sha256=model_digest(phase), files=tuple(values)
    )


def verify_raw_manifest(root: Path, manifest: RawManifest) -> None:
    """复验每个文件的存在、字节数、哈希及 JSONL 记录数。"""
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual != {item.path for item in manifest.files} | {"raw-manifest.json"}:
        raise ValueError("minimal_raw_file_set_mismatch")
    for item in manifest.files:
        payload = resolve_relative(root, item.path).read_bytes()
        if len(payload) != item.size_bytes or hashlib.sha256(payload).hexdigest() != item.sha256:
            raise ValueError("minimal_raw_hash_mismatch:" + item.path)
        if item.jsonl_records is not None and len(payload.splitlines()) != item.jsonl_records:
            raise ValueError("minimal_raw_record_count_mismatch:" + item.path)


def resolve_relative(root: Path, reference: str) -> Path:
    """拒绝宿主绝对路径、反斜线和穿越 Run 根的引用。"""
    path = Path(reference)
    if path.is_absolute() or "\\" in reference or ":" in reference or ".." in path.parts:
        raise ValueError("minimal_path_outside_root")
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError("minimal_path_outside_root")
    return candidate


def file_digest(path: Path) -> str:
    """文件字节哈希，不把路径或正文带入输出。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def yaml_digest(model: StrictModel) -> str:
    """重建冻结 YAML 的字节 commitment，不写文件。"""
    payload = yaml.safe_dump(model.model_dump(mode="json"), allow_unicode=True, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def verify_runtime_source(phase: MinimalPhaseContract, project_root: Path) -> None:
    """复算只能使用已冻结的 Runtime/分析代码，漂移时拒绝发布。"""
    for reference, expected in phase.runtime_source_sha256.items():
        if file_digest(resolve_relative(project_root, reference)) != expected:
            raise ValueError("minimal_runtime_source_drift")
