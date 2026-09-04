"""按清单顺序读回整张逻辑表，不遗漏后续分卷。"""

import csv
from collections.abc import Iterable, Iterator
from itertools import zip_longest
from pathlib import Path
from typing import TypeVar, cast

from skillflow.experiment.t17.v2.csv_export import csv_fields
from skillflow.experiment.t17.v2.frozen import inside
from skillflow.models.base import StrictModel

ModelT = TypeVar("ModelT", bound=StrictModel)
CSV_FIELD_LIMIT = 16 * 1024 * 1024


def jsonl_table_rows(root: Path, parts: tuple[str, ...], model: type[ModelT]) -> Iterator[ModelT]:
    """空行和损坏行都报错，不能跳过坏样本。"""
    for name in parts:
        with inside(root, name).open(encoding="utf-8") as stream:
            for line in stream:
                yield model.model_validate_json(line)


def csv_table_rows(root: Path, parts: tuple[str, ...]) -> Iterator[dict[str, str]]:
    """只拆分完整记录；每卷表头相同，支持字段内引号和换行。"""
    previous_limit = csv.field_size_limit(CSV_FIELD_LIMIT)
    columns = None
    try:
        for name in parts:
            with inside(root, name).open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                if columns is None:
                    columns = reader.fieldnames
                if not columns or columns != reader.fieldnames:
                    raise ValueError("v2_csv_part_header_drift")
                for row in reader:
                    if None in row or any(not isinstance(value, str) for value in row.values()):
                        raise ValueError("v2_csv_incomplete_record")
                    yield cast("dict[str, str]", row)
    finally:
        csv.field_size_limit(previous_limit)


def validate_csv_rows(root: Path, parts: tuple[str, ...], rows: Iterable[StrictModel]) -> None:
    """逐条比较复算值，避免把全部正式报告拼成巨大的内存字符串。"""
    for actual, expected in zip_longest(csv_table_rows(root, parts), (csv_fields(r) for r in rows)):
        if actual != expected:
            raise ValueError("v2_dataset_csv_recomputation_drift")
