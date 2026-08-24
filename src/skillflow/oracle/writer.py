"""Oracle JSONL 的独占写入入口。"""

from pathlib import Path

from skillflow.oracle.models import OracleTraceRecord
from skillflow.trace.jsonl import write_jsonl


class OracleTraceWriter:
    """为一次 Run 创建 oracle-trace.jsonl。"""

    def __init__(self, destination: Path) -> None:
        """固定一个不可覆盖的目标文件。"""
        self._destination = destination

    def write(self, records: tuple[OracleTraceRecord, ...]) -> None:
        """只序列化 sidecar 真值，不接触 EventStore 或 Blob。"""
        write_jsonl(self._destination, records)
