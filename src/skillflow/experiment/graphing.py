"""从 Experiment SQLite 重建脱敏安全图。"""

from pathlib import Path

from skillflow.experiment.locations import locate_run
from skillflow.graph.security import SecurityGraph
from skillflow.store.sqlite_store import SqliteEventStore


def graph_json(run_id: str, runs_root: Path) -> str:
    """返回一个 Run 的 Schema 化 JSON 图。"""
    located = locate_run(runs_root, run_id)
    with SqliteEventStore(located.experiment_root / "state.sqlite") as store:
        graph = SecurityGraph.from_store(store, run_id)
    return graph.to_export().model_dump_json(by_alias=True)
