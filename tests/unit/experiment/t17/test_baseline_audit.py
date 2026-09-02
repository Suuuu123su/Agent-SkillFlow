from datetime import UTC, datetime
from pathlib import Path

import pytest

from skillflow.experiment.t17.baseline_audit import (
    BaselineArtifactKind,
    BaselineArtifactMissingError,
    BaselineArtifactSelection,
    build_baseline_audit,
)
from skillflow.experiment.t17.contracts import EvidenceDomainKind


def test_baseline_audit_hashes_exact_bytes_and_keeps_domains_separate(tmp_path: Path) -> None:
    # Given: two canonical artifacts in different evidence domains.
    matrix = tmp_path / "matrix.yaml"
    matrix.write_bytes(b"matrix\r\n")
    summary = tmp_path / "summary.json"
    summary.write_bytes(b'{"status":"passed"}\n')
    selections = (
        BaselineArtifactSelection(
            Path("matrix.yaml"),
            BaselineArtifactKind.MATRIX,
            EvidenceDomainKind.SCRIPTED,
        ),
        BaselineArtifactSelection(
            Path("summary.json"),
            BaselineArtifactKind.SUMMARY,
            EvidenceDomainKind.DIRECT_PROMPT,
        ),
    )

    # When: T17-A builds the frozen audit.
    audit = build_baseline_audit(
        tmp_path,
        "deadbeef",
        datetime(2026, 9, 2, tzinfo=UTC),
        selections,
    )

    # Then: byte hashes and evidence domains are explicit and reproducible.
    assert len(audit.artifacts) == 2
    assert (
        audit.artifacts[0].sha256
        == "0040a3ff741a46ee104ad45d91d4747c13d86702ae06d1f9210e5c7975fc7bf5"
    )
    assert audit.artifacts[1].evidence_domain is EvidenceDomainKind.DIRECT_PROMPT


def test_baseline_audit_rejects_missing_canonical_artifact(tmp_path: Path) -> None:
    # Given: a selection naming a missing canonical artifact.
    selection = BaselineArtifactSelection(
        Path("missing.json"),
        BaselineArtifactKind.RAW_JSONL,
        EvidenceDomainKind.REFERENCE_HARNESS,
    )

    # When/Then: the audit fails instead of silently weakening its scope.
    with pytest.raises(BaselineArtifactMissingError):
        build_baseline_audit(
            tmp_path,
            "deadbeef",
            datetime(2026, 9, 2, tzinfo=UTC),
            (selection,),
        )
