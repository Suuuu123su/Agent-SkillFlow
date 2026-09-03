from pathlib import Path

import pytest

from skillflow.experiment.t17.minimal.artifacts import (
    build_raw_manifest,
    file_digest,
    freeze_minimal_configuration,
    freeze_phase,
    resolve_relative,
    validate_configuration,
    verify_raw_manifest,
    write_checked_json,
)
from skillflow.experiment.t17.minimal.run_models import MinimalPhaseContract
from skillflow.validation import DocumentValidationError


@pytest.fixture
def phase() -> MinimalPhaseContract:
    return MinimalPhaseContract(
        domain="scripted",
        configuration_sha256="a" * 64,
        matrix_sha256="b" * 64,
        runtime_source_sha256={"runtime.py": "c" * 64},
    )


def test_manifest_detects_content_record_count_and_unregistered_files(
    tmp_path: Path, phase: MinimalPhaseContract
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    path = raw / "records.jsonl"
    path.write_text("{}\n{}\n", encoding="utf-8")
    manifest = build_raw_manifest(raw, phase)
    write_checked_json(raw / "raw-manifest.json", manifest)
    verify_raw_manifest(raw, manifest)
    bad_record_count = manifest.model_copy(
        update={"files": (manifest.files[0].model_copy(update={"jsonl_records": 1}),)}
    )
    with pytest.raises(ValueError, match="record_count_mismatch"):
        verify_raw_manifest(raw, bad_record_count)
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="raw_hash_mismatch"):
        verify_raw_manifest(raw, manifest)
    (raw / "extra").write_text("not registered", encoding="utf-8")
    with pytest.raises(ValueError, match="file_set_mismatch"):
        verify_raw_manifest(raw, manifest)


@pytest.mark.parametrize("reference", ["../escape", "a/../../b", "scheme:value", "folder\\file"])
def test_relative_resolver_rejects_escape(tmp_path: Path, reference: str) -> None:
    with pytest.raises(ValueError, match="path_outside_root"):
        resolve_relative(tmp_path, reference)


def test_freeze_and_configuration_checks_are_exclusive_and_typed(tmp_path: Path) -> None:
    config = freeze_minimal_configuration(Path(), tmp_path / "inputs")
    loaded = validate_configuration(config, Path())
    phase = freeze_phase(config, Path(), "scripted")
    assert phase.configuration_sha256 == file_digest(config)
    assert loaded.expected_replay_pairs == 12
    with pytest.raises(FileExistsError):
        freeze_minimal_configuration(Path(), tmp_path / "inputs")
    content = config.read_text(encoding="utf-8").replace(
        "expected_replay_pairs: 12", "expected_replay_pairs: 11"
    )
    config.write_text(content, encoding="utf-8")
    with pytest.raises(DocumentValidationError, match="minimal_replay_count_drift"):
        validate_configuration(config, Path())
