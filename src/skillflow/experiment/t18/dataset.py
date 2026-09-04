"""公开本地证据与独立复算入口，不依赖私有运行目录或任何服务。"""

import hashlib
import json
from pathlib import Path
from typing import Literal

from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.experiment.t18.catalog_models import LocalCatalog
from skillflow.experiment.t18.matrix import Domain, LocalMatrix
from skillflow.experiment.t18.preregistration import Preregistration
from skillflow.experiment.t18.replay import LocalReplay
from skillflow.experiment.t18.report_data import AnalysisData, validate_data
from skillflow.experiment.t18.reporting import build_report, write_report
from skillflow.experiment.t18.run_models import LocalCore, LocalPhase
from skillflow.models.base import NonEmptyStr, StrictModel

REPORT_FILES = ("metrics.json", "summary.csv", "hiaa.csv")


class FileDigest(StrictModel):
    """公开文件的精确字节承诺。"""

    sha256: Sha256
    bytes: int


class DatasetManifest(StrictModel):
    """只登记本域文件，不把两种执行域合并为一次实验。"""

    schema_version: Literal["18.0"] = "18.0"
    domain: Domain
    core_count: int
    replay_count: int
    files: dict[NonEmptyStr, FileDigest]


def _put(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError("t18_dataset_existing_content_differs:" + path.name)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _digest(path: Path) -> FileDigest:
    content = path.read_bytes()
    return FileDigest(sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))


def export_dataset(data: AnalysisData, output: Path) -> DatasetManifest:
    """导出完整结构化事实；已有相同文件复用，不覆盖另一份结果。"""
    validate_data(data, verify=False)
    payloads: dict[str, StrictModel] = {
        "phase-contract.json": data.phase,
        "preregistration.json": data.config,
        "matrix.json": data.matrix,
        "catalog.json": data.catalog,
    }
    payloads.update({f"cores/c{i:03d}.json": c for i, c in enumerate(data.cores, 1)})
    payloads.update({f"replays/p{i:03d}.json": r for i, r in enumerate(data.replays, 1)})
    for name, model in payloads.items():
        _put(output / name, model.model_dump_json(indent=2) + "\n")
    write_report(output / "reports", build_report(data))
    names = sorted((*payloads, *("reports/" + name for name in REPORT_FILES)))
    manifest = DatasetManifest(
        domain=data.phase.domain,
        core_count=len(data.cores),
        replay_count=len(data.replays),
        files={name: _digest(output / name) for name in names},
    )
    _put(output / "manifest.json", manifest.model_dump_json(indent=2) + "\n")
    return manifest


def _check_manifest(directory: Path, manifest: DatasetManifest) -> None:
    root = directory.resolve()
    for name, expected in manifest.files.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or path == root:
            raise ValueError("t18_dataset_path_escape")
        if _digest(path) != expected:
            raise ValueError("t18_dataset_file_digest:" + name)
    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and p != root / "manifest.json"
    }
    if actual != set(manifest.files):
        raise ValueError("t18_dataset_unregistered_file")


def load_dataset(directory: Path, *, verify: bool = True) -> AnalysisData:
    """从公开集合读取，不访问当前项目配置或原始记录路径。"""
    manifest = DatasetManifest.model_validate_json(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )
    if verify:
        _check_manifest(directory, manifest)
    phase = LocalPhase.model_validate_json(
        (directory / "phase-contract.json").read_text(encoding="utf-8")
    )
    config = Preregistration.model_validate_json(
        (directory / "preregistration.json").read_text(encoding="utf-8")
    )
    matrix = LocalMatrix.model_validate_json(
        (directory / "matrix.json").read_text(encoding="utf-8")
    )
    catalog = LocalCatalog.model_validate_json(
        (directory / "catalog.json").read_text(encoding="utf-8")
    )
    cores = tuple(
        LocalCore.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted((directory / "cores").glob("*.json"))
    )
    replays = tuple(
        LocalReplay.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted((directory / "replays").glob("*.json"))
    )
    if (
        manifest.domain != phase.domain
        or manifest.core_count != len(cores)
        or manifest.replay_count != len(replays)
    ):
        raise ValueError("t18_dataset_record_count_or_domain")
    data = AnalysisData(phase, config, matrix, catalog, matrix.cores, cores, replays)
    validate_data(data, verify=verify)
    return data


def recompute_dataset(directory: Path, output: Path) -> dict[str, str | int]:
    """由公开事实重新计算所有正式 JSON/CSV，逐字节核对，不执行新任务。"""
    if output.resolve().is_relative_to(directory.resolve()):
        raise ValueError("t18_recompute_requires_separate_output")
    data = load_dataset(directory)
    write_report(output, build_report(data))
    for name in REPORT_FILES:
        if (output / name).read_bytes() != (directory / "reports" / name).read_bytes():
            raise ValueError("t18_independent_recompute_mismatch:" + name)
    result: dict[str, str | int] = {
        "status": "pass",
        "domain": data.phase.domain,
        "core_count": len(data.cores),
        "replay_pairs": len(data.replays),
        "compared_files": len(REPORT_FILES),
        "api_calls": 0,
    }
    _put(output / "recompute-status.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result
