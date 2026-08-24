import json
from pathlib import Path

import networkx as nx
import pytest

from skillflow.graph.enums import GraphNodeKind, ProvenanceRelation, SecurityRelation
from skillflow.graph.errors import GraphExportError
from skillflow.graph.models import SecurityGraphExport
from skillflow.graph.security import SecurityGraph
from skillflow.store.sqlite_store import SqliteEventStore
from tests.integration.graph.golden_fixture import PAYLOAD_MARKER, build_golden_store


def test_builder_reconstructs_bipartite_core_and_closed_semantic_projection(
    tmp_path: Path,
) -> None:
    # Given: 包含跨会话、授权、撤销与 Effect 的真实 SQLite EventStore
    ids = build_golden_store(tmp_path)

    # When: 只从 EventStore 重建双层来源图
    with SqliteEventStore(ids.database_path) as store:
        graph = SecurityGraph.from_store(store, ids.run_id)
    exported = graph.to_export()

    # Then: 核心边严格保持 Artifact→Event→Artifact 二部方向
    assert nx.is_frozen(graph.provenance_graph)
    assert {reference.kind for reference in graph.provenance_graph.nodes} <= {
        GraphNodeKind.ARTIFACT,
        GraphNodeKind.EVENT,
    }
    assert all(
        (
            edge.source.kind is GraphNodeKind.ARTIFACT
            and edge.target.kind is GraphNodeKind.EVENT
            and edge.relation is ProvenanceRelation.USED
        )
        or (
            edge.source.kind is GraphNodeKind.EVENT
            and edge.target.kind is GraphNodeKind.ARTIFACT
            and edge.relation is ProvenanceRelation.GENERATED
        )
        for edge in exported.provenance_edges
    )
    relations = {edge.relation for edge in exported.security_edges}
    assert {
        SecurityRelation.READ,
        SecurityRelation.WRITE,
        SecurityRelation.LOAD,
        SecurityRelation.INVOKE,
        SecurityRelation.DERIVE,
        SecurityRelation.PERSIST,
        SecurityRelation.AUTHORIZE,
        SecurityRelation.INFLUENCE_CANDIDATE,
        SecurityRelation.REVOKE,
    } <= relations
    assert SecurityRelation.INFLUENCE_CONFIRMED not in relations


def test_security_graph_is_read_only_after_construction(tmp_path: Path) -> None:
    # Given: 已从事实源构建完成的图
    ids = build_golden_store(tmp_path)
    with SqliteEventStore(ids.database_path) as store:
        graph = SecurityGraph.from_store(store, ids.run_id)

    # When: 取得公开的 SecurityGraph 快照
    snapshot = graph.security_graph

    # Then: NetworkX 会拒绝调用方修改节点或边
    assert nx.is_frozen(snapshot)


def test_json_export_is_typed_deterministic_and_drops_raw_secrets(tmp_path: Path) -> None:
    # Given: Blob 与 Event metadata 都含秘密哨兵的 Golden Store
    ids = build_golden_store(tmp_path)
    with SqliteEventStore(ids.database_path) as store:
        graph = SecurityGraph.from_store(store, ids.run_id)
    output = tmp_path / "security-graph.json"

    # When: 导出允许字段组成的 JSON
    graph.export_json(output)

    # Then: 输出可由强类型模型读回，且不含原文或任意 metadata
    text = output.read_text(encoding="utf-8")
    parsed = SecurityGraphExport.model_validate(json.loads(text))
    assert parsed.run_id == ids.run_id
    assert PAYLOAD_MARKER not in text
    assert "metadata" not in text


def test_json_export_refuses_to_overwrite_existing_evidence(tmp_path: Path) -> None:
    ids = build_golden_store(tmp_path)
    with SqliteEventStore(ids.database_path) as store:
        graph = SecurityGraph.from_store(store, ids.run_id)
    output = tmp_path / "security-graph.json"
    graph.export_json(output)

    with pytest.raises(GraphExportError):
        graph.export_json(output)
