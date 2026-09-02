import json
from pathlib import Path

from typer.testing import CliRunner

from skillflow.cli import app


def test_t17_audit_baseline_writes_complete_canonical_manifest(tmp_path: Path) -> None:
    # Given: a new output path and the current checkout as the canonical source.
    output = tmp_path / "t17-baseline-audit.json"

    # When: the public T17 CLI freezes the baseline.
    result = CliRunner().invoke(
        app,
        [
            "t17",
            "audit-baseline",
            "--project-root",
            ".",
            "--source-revision",
            "test-revision",
            "--output",
            str(output),
        ],
    )

    # Then: it succeeds and records every selected artifact with a unique path.
    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    paths = [item["path"] for item in payload["artifacts"]]
    assert payload["artifact_count"] >= 24
    assert len(paths) == len(set(paths))
    assert payload["source_revision"] == "test-revision"
