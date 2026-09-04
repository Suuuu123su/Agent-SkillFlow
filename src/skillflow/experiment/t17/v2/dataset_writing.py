"""不可覆盖的数据文件写入及有界凭据、宿主路径检查。"""

import re
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

from skillflow.experiment.t17.v2.canonical import canonical_text
from skillflow.experiment.t17.v2.csv_export import csv_header, csv_records
from skillflow.experiment.t17.v2.dataset_models import DatasetFile
from skillflow.experiment.t17.v2.frozen import file_digest, inside
from skillflow.models.base import StrictModel

MAX_PUBLIC_BYTES = 90 * 1024 * 1024
MAX_TABLE_BYTES = 16 * 1024 * 1024
_SECRET = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
_HOST_PATH = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z]:[\\/]|\\\\\\\\[A-Za-z0-9]")
_SCHEMA_DOCUMENT = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}
_TEXT_DOCUMENT = {"type": "string"}


def guard_public(text: str) -> None:
    """错误只暴露类别，不能把匹配到的秘密原文再次写进错误报告。"""
    if _SECRET.search(text):
        raise ValueError("v2_public_credential_detected")
    if _HOST_PATH.search(text):
        raise ValueError("v2_public_host_path_detected")


class DatasetWriter:
    """新目录内机械生成格式、记录数与哈希，不修改已有文件。"""

    def __init__(self, root: Path, directory: Path) -> None:
        """所有输出必须在项目内且目标目录尚不存在。"""
        self.directory = inside(
            root.resolve(), directory.resolve().relative_to(root.resolve()).as_posix()
        )
        self.directory.mkdir(parents=True, exist_ok=False)
        self.files: dict[str, DatasetFile] = {}
        self.tables: dict[str, tuple[str, ...]] = {}
        self._schemas: set[str] = set()
        self._raw("schemas/schema-document.schema.json", canonical_text(_SCHEMA_DOCUMENT) + "\n")
        self._record(
            "schemas/schema-document.schema.json", "schemas/schema-document.schema.json", "json", 1
        )
        self._raw("schemas/text-document.schema.json", canonical_text(_TEXT_DOCUMENT) + "\n")
        self._record(
            "schemas/text-document.schema.json", "schemas/schema-document.schema.json", "json", 1
        )

    def schema_for(self, model: type[StrictModel]) -> str:
        """静态格式定义完全由类型模型生成，并立即检查格式合法性。"""
        name = "schemas/" + model.__name__ + ".schema.json"
        if name not in self._schemas:
            schema = model.model_json_schema()
            Draft202012Validator.check_schema(schema)
            self._raw(name, canonical_text(schema) + "\n")
            self._record(name, "schemas/schema-document.schema.json", "json", 1)
            self._schemas.add(name)
        return name

    def model(self, name: str, value: StrictModel) -> None:
        """每份 JSON 保存完整强类型值，而不是随意拼接字段。"""
        schema = self.schema_for(type(value))
        self._raw(name, canonical_text(value) + "\n")
        self._record(name, schema, "json", 1)

    def rows(self, name: str, rows: Iterable[StrictModel], model: type[StrictModel]) -> None:
        """按完整记录分卷，空表也明确记录为零行。"""
        schema = self.schema_for(model)

        def lines() -> Iterable[str]:
            for row in rows:
                if not isinstance(row, model):
                    raise TypeError("v2_dataset_row_schema_mismatch")
                yield canonical_text(row) + "\n"

        self._table(name, lines(), schema, "jsonl", "")

    def csv(self, name: str, rows: Iterable[StrictModel], model: type[StrictModel]) -> None:
        """字段名由同一个扁平模型生成，CSV 与 JSON 不维护两套公式。"""
        columns = tuple(model.model_fields)
        self._table(
            name, csv_records(rows, columns), self.schema_for(model), "csv", csv_header(columns)
        )

    def _table(
        self, name: str, rows: Iterable[str], schema: str, format_name: str, header: str
    ) -> None:
        parts: list[str] = []
        lines: list[str] = []
        size = len(header.encode())

        def flush() -> None:
            path = PurePosixPath(name)
            part = (
                name
                if not parts
                else str(path.with_name(f"{path.stem}.part-{len(parts) + 1:04d}{path.suffix}"))
            )
            self._raw(part, header + "".join(lines))
            self._record(part, schema, format_name, len(lines))
            parts.append(part)

        for row in rows:
            row_size = len(row.encode())
            if row_size + len(header.encode()) > MAX_TABLE_BYTES:
                raise ValueError("v2_public_row_size_limit")
            if lines and size + row_size > MAX_TABLE_BYTES:
                flush()
                lines = []
                size = len(header.encode())
            lines.append(row)
            size += row_size
        flush()
        self.tables[name] = tuple(parts)

    def text(self, name: str, text: str) -> None:
        """说明文件也受目录、凭据和体积约束。"""
        self._raw(name, text)
        self._record(name, "schemas/text-document.schema.json", "text", len(text.splitlines()))

    def _raw(self, name: str, text: str) -> None:
        guard_public(text)
        if len(text.encode()) > MAX_PUBLIC_BYTES:
            raise ValueError("v2_public_file_size_limit")
        path = inside(self.directory, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)

    def _record(self, name: str, schema: str, format_name: str, count: int) -> None:
        self.files[name] = DatasetFile.model_validate(
            {
                "content": file_digest(inside(self.directory, name)),
                "schema_path": schema,
                "record_count": count,
                "format": format_name,
            }
        )
