"""T17-A 对既有 canonical 证据执行只读字节级冻结。"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum, unique
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from skillflow.experiment.io import write_json_model
from skillflow.experiment.t17.contracts import EvidenceDomainKind
from skillflow.models.base import NonEmptyStr, StrictModel

Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonNegativeInt = Annotated[int, Field(ge=0)]


@unique
class BaselineArtifactKind(StrEnum):
    """T17-A 冻结证据允许的文件角色。"""

    MATRIX = "matrix"
    PREREGISTRATION = "preregistration"
    PROMPT_CONTRACT = "prompt_contract"
    RAW_JSONL = "raw_jsonl"
    SUMMARY = "summary"
    SCHEMA = "schema"
    MANIFEST = "manifest"
    REPORT = "report"


@dataclass(frozen=True, slots=True)
class BaselineArtifactSelection:
    """一个项目相对路径及其固定证据角色。"""

    path: Path
    kind: BaselineArtifactKind
    evidence_domain: EvidenceDomainKind


@dataclass(frozen=True, slots=True)
class BaselineArtifactMissingError(FileNotFoundError):
    """canonical 证据不存在，审计不能降级继续。"""

    path: Path

    def __str__(self) -> str:
        """返回稳定的项目相对路径诊断。"""
        return f"T17-A canonical 证据缺失: {self.path.as_posix()}"


class BaselineArtifactRecord(StrictModel):
    """一个旧文件的路径、角色和字节级摘要。"""

    path: NonEmptyStr
    kind: BaselineArtifactKind
    evidence_domain: EvidenceDomainKind
    sha256: Sha256Hex
    byte_length: NonNegativeInt


class T17BaselineAudit(StrictModel):
    """T12-T16 canonical 输入与结果的不可混域索引。"""

    schema_version: Literal["0.1"] = "0.1"
    created_at: AwareDatetime
    source_revision: NonEmptyStr
    artifact_count: NonNegativeInt
    artifact_set_sha256: Sha256Hex
    artifacts: tuple[BaselineArtifactRecord, ...]


def build_baseline_audit(
    project_root: Path,
    source_revision: str,
    created_at: datetime,
    selections: tuple[BaselineArtifactSelection, ...],
) -> T17BaselineAudit:
    """按项目相对路径排序并冻结每个 canonical 文件的精确字节。"""
    records: list[BaselineArtifactRecord] = []
    for selection in sorted(selections, key=lambda item: item.path.as_posix()):
        absolute = project_root / selection.path
        if not absolute.is_file():
            raise BaselineArtifactMissingError(selection.path)
        content = absolute.read_bytes()
        records.append(
            BaselineArtifactRecord(
                path=selection.path.as_posix(),
                kind=selection.kind,
                evidence_domain=selection.evidence_domain,
                sha256=hashlib.sha256(content).hexdigest(),
                byte_length=len(content),
            )
        )
    encoded = "\n".join(f"{item.path}:{item.sha256}" for item in records).encode()
    return T17BaselineAudit(
        created_at=created_at,
        source_revision=source_revision,
        artifact_count=len(records),
        artifact_set_sha256=hashlib.sha256(encoded).hexdigest(),
        artifacts=tuple(records),
    )


def write_baseline_audit(path: Path, audit: T17BaselineAudit) -> None:
    """以不可覆盖方式写出 T17-A 审计。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_model(path, audit)


def canonical_baseline_selections(project_root: Path) -> tuple[BaselineArtifactSelection, ...]:
    """返回 T12-T16 已确认为研究证据的最小 canonical 文件集。"""
    selections = [
        _selection(
            "scenarios/matrix/mvp.yaml", BaselineArtifactKind.MATRIX, EvidenceDomainKind.SCRIPTED
        ),
        _selection(
            "runs/mvp/experiment-manifest.json",
            BaselineArtifactKind.MANIFEST,
            EvidenceDomainKind.SCRIPTED,
        ),
        _selection(
            "runs/mvp/experiment-report.json",
            BaselineArtifactKind.REPORT,
            EvidenceDomainKind.SCRIPTED,
        ),
        _selection(
            "experiments/t16/preregistration.yaml",
            BaselineArtifactKind.PREREGISTRATION,
            EvidenceDomainKind.FAKE_PROVIDER,
        ),
        _selection(
            "experiments/t16/t16b_fake_dry_run.yaml",
            BaselineArtifactKind.MATRIX,
            EvidenceDomainKind.FAKE_PROVIDER,
        ),
        _selection(
            "docs/evidence/t16b-fake-run-summary.json",
            BaselineArtifactKind.SUMMARY,
            EvidenceDomainKind.FAKE_PROVIDER,
        ),
        _selection(
            "experiments/t16/preregistration_t16c_v2.yaml",
            BaselineArtifactKind.PREREGISTRATION,
            EvidenceDomainKind.DIRECT_PROMPT,
        ),
        _selection(
            "experiments/t16/matrix_smoke_t16c_v2.yaml",
            BaselineArtifactKind.MATRIX,
            EvidenceDomainKind.DIRECT_PROMPT,
        ),
        _selection(
            "experiments/t16/matrix_model1_t16c_v2.yaml",
            BaselineArtifactKind.MATRIX,
            EvidenceDomainKind.DIRECT_PROMPT,
        ),
        _selection(
            "runs/t16c-v2-live-20260829-01/attempt-01/smoke/trial-results.jsonl",
            BaselineArtifactKind.RAW_JSONL,
            EvidenceDomainKind.DIRECT_PROMPT,
        ),
        _selection(
            "runs/t16c-v2-live-20260829-01/attempt-01/model1/trial-results.jsonl",
            BaselineArtifactKind.RAW_JSONL,
            EvidenceDomainKind.DIRECT_PROMPT,
        ),
        _selection(
            "docs/evidence/t16c-v2-live-summary-20260829.json",
            BaselineArtifactKind.SUMMARY,
            EvidenceDomainKind.DIRECT_PROMPT,
        ),
        _selection(
            "experiments/t16/preregistration_task_success_v3.yaml",
            BaselineArtifactKind.PREREGISTRATION,
            EvidenceDomainKind.REFERENCE_HARNESS,
        ),
        _selection(
            "experiments/t16/preregistration_task_success_v3_1.yaml",
            BaselineArtifactKind.PREREGISTRATION,
            EvidenceDomainKind.REFERENCE_HARNESS,
        ),
        _selection(
            "experiments/t16/matrix_task_success_smoke_v3.yaml",
            BaselineArtifactKind.MATRIX,
            EvidenceDomainKind.REFERENCE_HARNESS,
        ),
        _selection(
            "experiments/t16/task_success_assertions_v3.yaml",
            BaselineArtifactKind.PROMPT_CONTRACT,
            EvidenceDomainKind.REFERENCE_HARNESS,
        ),
        _selection(
            "runs/t16d2-v3-live-20260829-01/attempt-01/raw-trials.jsonl",
            BaselineArtifactKind.RAW_JSONL,
            EvidenceDomainKind.REFERENCE_HARNESS,
        ),
        _selection(
            "runs/t16d2-v3-live-20260829-01/attempt-01/run-summary.json",
            BaselineArtifactKind.SUMMARY,
            EvidenceDomainKind.REFERENCE_HARNESS,
        ),
        _selection(
            "runs/t16d2-v31-canary-live-20260830-01/attempt-01/raw-trials.jsonl",
            BaselineArtifactKind.RAW_JSONL,
            EvidenceDomainKind.REFERENCE_HARNESS,
        ),
        _selection(
            "runs/t16d2-v31-canary-live-20260830-01/attempt-01/run-summary.json",
            BaselineArtifactKind.SUMMARY,
            EvidenceDomainKind.REFERENCE_HARNESS,
        ),
        _selection(
            "experiments/t16/t16e_second_model.yaml",
            BaselineArtifactKind.PREREGISTRATION,
            EvidenceDomainKind.REFERENCE_HARNESS,
        ),
        _selection(
            "runs/t16e-model2-gpt55-live-20260831-01/attempt-01/raw-trials.jsonl",
            BaselineArtifactKind.RAW_JSONL,
            EvidenceDomainKind.REFERENCE_HARNESS,
        ),
        _selection(
            "runs/t16e-model2-gpt55-live-20260831-01/attempt-01/run-summary.json",
            BaselineArtifactKind.SUMMARY,
            EvidenceDomainKind.REFERENCE_HARNESS,
        ),
        _selection(
            "docs/summaries/T16E_Summary.md",
            BaselineArtifactKind.SUMMARY,
            EvidenceDomainKind.REFERENCE_HARNESS,
        ),
    ]
    selections.extend(
        BaselineArtifactSelection(
            path.relative_to(project_root),
            BaselineArtifactKind.SCHEMA,
            EvidenceDomainKind.CONTRACT,
        )
        for path in sorted((project_root / "schemas").glob("t16*.schema.json"))
    )
    return tuple(selections)


def _selection(
    path: str,
    kind: BaselineArtifactKind,
    domain: EvidenceDomainKind,
) -> BaselineArtifactSelection:
    return BaselineArtifactSelection(Path(path), kind, domain)
