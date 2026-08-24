"""只读 SecurityGraph 门面、七类研究查询与 JSON 导出。"""

from collections import defaultdict
from pathlib import Path

import networkx as nx

from skillflow.graph.builder import build_graph_data
from skillflow.graph.enums import GraphNodeKind
from skillflow.graph.errors import GraphExportError, GraphRunMismatchError
from skillflow.graph.models import (
    GraphBuildData,
    GraphNodeRef,
    RevocationFact,
    SecurityGraphExport,
    SecurityPath,
    node_ref,
)
from skillflow.graph.pathing import (
    DEFAULT_MAX_DEPTH,
    GraphPathFinder,
    PathContext,
    PathRequest,
    SecurityDiGraph,
)
from skillflow.store.event_store import EventStore


class SecurityGraph:
    """从一个 Run 的 EventStore 事实构建的冻结查询视图。"""

    def __init__(self, data: GraphBuildData) -> None:
        """从已校验的构建数据创建两张冻结的有向图。"""
        self._data = data
        self._nodes = {node_ref(node): node for node in data.nodes}
        self._provenance: SecurityDiGraph = nx.DiGraph()
        self._provenance.add_nodes_from(
            reference
            for reference in self._nodes
            if reference.kind in {GraphNodeKind.ARTIFACT, GraphNodeKind.EVENT}
        )
        self._provenance.add_edges_from(
            (edge.source, edge.target) for edge in data.provenance_edges
        )
        nx.freeze(self._provenance)
        self._security: SecurityDiGraph = nx.DiGraph()
        self._security.add_nodes_from(self._nodes)
        self._security.add_edges_from((edge.source, edge.target) for edge in data.security_edges)
        nx.freeze(self._security)
        edges = {(edge.source, edge.target): edge for edge in data.security_edges}
        raw_index: dict[str, list[GraphNodeRef]] = defaultdict(list)
        for reference in self._nodes:
            raw_index[reference.node_id].append(reference)
        revocations: dict[GraphNodeRef, list[RevocationFact]] = defaultdict(list)
        for fact in data.revocations:
            revocations[fact.target].append(fact)
        self._finder = GraphPathFinder(
            PathContext(
                graph=self._security,
                nodes=self._nodes,
                edges=edges,
                raw_index={key: tuple(value) for key, value in raw_index.items()},
                revocations={key: tuple(value) for key, value in revocations.items()},
            )
        )

    @classmethod
    def from_store(cls, store: EventStore, run_id: str) -> "SecurityGraph":
        """从唯一事实源重建视图，不读取 Oracle 或 Trace Writer。"""
        return cls(build_graph_data(store, run_id))

    @property
    def provenance_graph(self) -> SecurityDiGraph:
        """返回与内部状态隔离的冻结二部图快照。"""
        return _frozen_copy(self._provenance)

    @property
    def security_graph(self) -> SecurityDiGraph:
        """返回与内部状态隔离的冻结安全视图快照。"""
        return _frozen_copy(self._security)

    def find_ancestors(
        self,
        artifact_id: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> tuple[SecurityPath, ...]:
        """查找全部可达祖先到指定 Artifact 的有限简单路径。"""
        artifact = self._finder.resolve(artifact_id, GraphNodeKind.ARTIFACT)
        return self._finder.ancestors(artifact, max_depth)

    def find_paths(
        self,
        source_id: str,
        sink_id: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> tuple[SecurityPath, ...]:
        """查找两个唯一类型化节点之间的全部有限简单路径。"""
        source = self._finder.resolve(source_id)
        sink = self._finder.resolve(sink_id)
        return self._finder.search(PathRequest((source,), (sink,), max_depth))

    def find_untrusted_paths(
        self,
        effect_id: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> tuple[SecurityPath, ...]:
        """查找所有不可信 Artifact 到指定 Effect 的路径。"""
        effect = self._finder.resolve(effect_id, GraphNodeKind.EFFECT)
        return self._finder.untrusted(effect, max_depth)

    def find_authorization_path(
        self,
        effect_id: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> tuple[SecurityPath, ...]:
        """查找 AUTH_GRANT 或 Grant 节点到指定 Effect 的授权路径。"""
        effect = self._finder.resolve(effect_id, GraphNodeKind.EFFECT)
        return self._finder.authorization(effect, max_depth)

    def find_revoked_ancestors(
        self,
        effect_id: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> tuple[SecurityPath, ...]:
        """查找在 Effect 时点前已经撤销的可达祖先路径。"""
        effect = self._finder.resolve(effect_id, GraphNodeKind.EFFECT)
        return self._finder.revoked(effect, max_depth)

    def find_cross_session_paths(
        self,
        run_id: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> tuple[SecurityPath, ...]:
        """查找指定 Run 中发生至少一次 Session 转换的 Effect 路径。"""
        if run_id != self._data.run_id:
            raise GraphRunMismatchError(self._data.run_id, run_id)
        return self._finder.cross_session(max_depth)

    def find_skill_to_effect_paths(
        self,
        skill_id: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> tuple[SecurityPath, ...]:
        """查找指定 Skill 到全部 Effect 的候选影响路径。"""
        skill = self._finder.resolve(skill_id, GraphNodeKind.PRINCIPAL)
        return self._finder.skill_effects(skill, max_depth)

    def to_export(self) -> SecurityGraphExport:
        """构造只包含允许字段的确定 JSON 模型。"""
        return SecurityGraphExport(
            run_id=self._data.run_id,
            nodes=self._data.nodes,
            provenance_edges=self._data.provenance_edges,
            security_edges=self._data.security_edges,
        )

    def export_json(self, path: Path) -> None:
        """以 exclusive-create 写入脱敏 JSON，拒绝覆盖现有文件。"""
        try:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(self.to_export().model_dump_json(indent=2))
                stream.write("\n")
        except OSError as error:
            raise GraphExportError(path, str(error)) from error


def _frozen_copy(graph: SecurityDiGraph) -> SecurityDiGraph:
    copy: SecurityDiGraph = nx.DiGraph()
    copy.add_nodes_from(graph.nodes)
    copy.add_edges_from(graph.edges)
    nx.freeze(copy)
    return copy
