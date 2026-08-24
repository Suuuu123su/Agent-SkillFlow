"""从 EventStore 事实构建二部图与 SecurityGraph 投影。"""

from skillflow.graph.assembly import GraphAssembler
from skillflow.graph.event_projection import project_events
from skillflow.graph.facts import load_run_graph_facts
from skillflow.graph.models import GraphBuildData
from skillflow.graph.record_projection import project_records
from skillflow.store.event_store import EventStore


def build_graph_data(store: EventStore, run_id: str) -> GraphBuildData:
    """从唯一事实源完成确定性图投影。"""
    facts = load_run_graph_facts(store, run_id)
    assembler = GraphAssembler(run_id)
    project_events(assembler, facts)
    project_records(assembler, facts)
    return assembler.finish()
