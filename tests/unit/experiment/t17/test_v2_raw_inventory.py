"""交付清单复用旧登记，只计算缺项，不触碰旧记录和正在运行的尝试。"""

import json
from pathlib import Path

import pytest

from skillflow.experiment.t17.v2.frozen import FrozenFile, file_digest


@pytest.mark.parametrize("manifest_name", ["raw-manifest.json", "continuation-manifest.json"])
def test_inventory_reuses_existing_hash_and_adds_private_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, manifest_name: str
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[4] / "scripts/t17_delivery"))
    import t17_raw_inventory  # noqa: PLC0415

    scope = tmp_path / "runs/sample"
    raw = scope / "raw"
    private = raw / "api-private/000001.json"
    private.parent.mkdir(parents=True)
    private.write_text('{"private_body":"not for publication"}', encoding="utf-8")
    known = raw / "known.txt"
    known.write_text("registered", encoding="utf-8")
    original = file_digest(known)
    manifest = raw / manifest_name
    manifest.write_text(
        json.dumps({"files": {"known.txt": original.model_dump(mode="json")}}), encoding="utf-8"
    )
    duplicate = scope / "dataset/private-copy.json"
    duplicate.parent.mkdir()
    duplicate.write_text("separately delivered", encoding="utf-8")
    digested: list[Path] = []

    def track(path: Path) -> FrozenFile:
        digested.append(path)
        return file_digest(path)

    monkeypatch.setattr(t17_raw_inventory, "file_digest", track)
    rows = t17_raw_inventory.collect_inventory(tmp_path, ("runs/sample",))
    by_path = {row.path: row for row in rows}
    assert len(rows) == 3
    assert by_path["runs/sample/raw/known.txt"].content == original
    assert by_path["runs/sample/raw/known.txt"].basis == "existing_registration"
    assert by_path["runs/sample/raw/api-private/000001.json"].basis == "first_registration"
    assert known not in digested
    assert private in digested
    assert "private_body" not in "".join(row.model_dump_json() for row in rows)


def test_inventory_rejects_registered_size_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[4] / "scripts/t17_delivery"))
    from t17_raw_inventory import collect_inventory  # noqa: PLC0415

    raw = tmp_path / "runs/sample/raw"
    raw.mkdir(parents=True)
    known = raw / "known.txt"
    known.write_text("old", encoding="utf-8")
    content = file_digest(known).model_dump(mode="json")
    (raw / "raw-manifest.json").write_text(
        json.dumps({"files": {"known.txt": content}}), encoding="utf-8"
    )
    known.write_text("changed size", encoding="utf-8")
    with pytest.raises(ValueError, match="raw_inventory_registered_size_changed"):
        collect_inventory(tmp_path, ("runs/sample",))


def test_inventory_rejects_open_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[4] / "scripts/t17_delivery"))
    from t17_raw_inventory import collect_inventory  # noqa: PLC0415

    (tmp_path / "runs/sample/model2/attempt-02").mkdir(parents=True)
    with pytest.raises(ValueError, match="raw_inventory_attempt_not_closed"):
        collect_inventory(tmp_path, ("runs/sample",))


def test_inventory_follows_explicit_correction_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[4] / "scripts/t17_delivery"))
    from t17_raw_inventory import collect_inventory  # noqa: PLC0415

    original = tmp_path / "runs/sample/original"
    correction = tmp_path / "runs/sample/corrected"
    for directory in (original, correction):
        (directory / "terminals").mkdir(parents=True)
    raw = original / "receipt.json"
    raw.write_text("{}", encoding="utf-8")
    content = file_digest(raw)
    terminal = json.dumps({"raw_files": {"receipt.json": content.model_dump(mode="json")}})
    paths = [directory / "terminals/unit.json" for directory in (original, correction)]
    for path in paths:
        path.write_text(terminal, encoding="utf-8")
    (correction / "correction.json").write_text(
        json.dumps(
            {
                "original_replay_path": paths[0].relative_to(tmp_path).as_posix(),
                "corrected_replay_path": paths[1].relative_to(tmp_path).as_posix(),
                "original_replay_file": file_digest(paths[0]).model_dump(mode="json"),
                "corrected_replay_file": file_digest(paths[1]).model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )
    rows = collect_inventory(tmp_path, ("runs/sample",))
    by_path = {row.path: row for row in rows}
    assert len(rows) == 4
    assert by_path["runs/sample/original/receipt.json"].content == content
    assert "runs/sample/corrected/receipt.json" not in by_path
    paths[1].write_text('{"raw_files": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="raw_inventory_correction_source_mismatch"):
        collect_inventory(tmp_path, ("runs/sample",))
