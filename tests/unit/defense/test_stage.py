from pathlib import Path

import pytest

from skillflow.experiment.t18.stage import run_batch

ROOT = Path(__file__).resolve().parents[3]


def test_stage_resumes_without_repeating_core(t17_cli_root: Path) -> None:
    output = t17_cli_root / "t18-stage-test"
    first = run_batch(ROOT, output, "scripted", 2)
    assert first["completed"] == 2
    terminal = output / "terminals/c001.json"
    first_bytes = terminal.read_bytes()
    first_time = terminal.stat().st_mtime_ns
    second = run_batch(ROOT, output, "scripted", 1)
    assert second["completed"] == 3
    assert second["new_core"] == 1
    assert terminal.read_bytes() == first_bytes
    assert terminal.stat().st_mtime_ns == first_time


def test_stage_rejects_oversized_batch_and_unsafe_output(t17_cli_root: Path) -> None:
    with pytest.raises(ValueError, match="short_batch"):
        run_batch(ROOT, t17_cli_root / "t18-no-run", "scripted", 49)
    with pytest.raises(ValueError, match="new_project_directory"):
        run_batch(ROOT, ROOT, "scripted", 1)
