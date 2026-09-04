"""文件分卷必须保留全部记录、CSV 引号换行和确定的顺序。"""

from pathlib import Path

import pytest

from skillflow.experiment.t17.v2 import dataset_writing
from skillflow.experiment.t17.v2.dataset_tables import csv_table_rows, jsonl_table_rows
from skillflow.experiment.t17.v2.dataset_writing import DatasetWriter
from skillflow.models.base import StrictModel


class Row(StrictModel):
    name: str
    value: int


def test_small_shards_restore_jsonl_and_quoted_csv(
    t17_cli_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dataset_writing, "MAX_TABLE_BYTES", 400)
    directory = t17_cli_root / "parts"
    writer = DatasetWriter(Path.cwd(), directory)
    rows = tuple(Row(name=('文本,"\n' * 6) + str(i), value=i) for i in range(20))
    writer.rows("facts.jsonl", rows, Row)
    writer.csv("facts.csv", rows, Row)
    for name in ("facts.jsonl", "facts.csv"):
        assert len(writer.tables[name]) > 1
        assert writer.tables[name][0] == name
        assert sum(writer.files[p].record_count for p in writer.tables[name]) == 20
        assert all((directory / p).stat().st_size <= 400 for p in writer.tables[name])
    assert tuple(jsonl_table_rows(directory, writer.tables["facts.jsonl"], Row)) == rows
    csv_rows = tuple(csv_table_rows(directory, writer.tables["facts.csv"]))
    assert [row["name"] for row in csv_rows] == [row.name for row in rows]
    assert [int(row["value"]) for row in csv_rows] == list(range(20))


def test_empty_table_keeps_one_file_and_oversize_row_is_rejected(
    t17_cli_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dataset_writing, "MAX_TABLE_BYTES", 100)
    writer = DatasetWriter(Path.cwd(), t17_cli_root / "empty-parts")
    writer.rows("empty.jsonl", (), Row)
    assert writer.tables["empty.jsonl"] == ("empty.jsonl",)
    assert writer.files["empty.jsonl"].record_count == 0
    with pytest.raises(ValueError, match="v2_public_row_size_limit"):
        writer.rows("large.jsonl", (Row(name="x" * 300, value=0),), Row)
