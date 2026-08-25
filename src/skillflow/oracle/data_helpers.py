"""Oracle 数据来源投影的无状态辅助函数。"""

from collections.abc import Iterable

from skillflow.models.scenario_parts import AssetSpec
from skillflow.oracle.errors import OracleInvariantError
from skillflow.oracle.models import OracleArtifactTrace, OracleReceiptEvidence


def workspace_resource(asset: AssetSpec) -> str:
    """把 fixture 资产机械映射到 Run workspace 资源。"""
    prefix = "fixture://"
    if not asset.uri.root.startswith(prefix):
        raise OracleInvariantError(
            "asset_projection",
            f"T06 asset 必须使用 fixture://：{asset.uri.root}",
        )
    return f"workspace:/{asset.uri.root.removeprefix(prefix)}"


def origins(records: Iterable[OracleArtifactTrace]) -> tuple[str, ...]:
    """返回去重并排序后的 GT_data 来源。"""
    return tuple(sorted(origin_set(records)))


def origin_set(records: Iterable[OracleArtifactTrace]) -> set[str]:
    """把多条 Oracle Artifact 的 GT_data 合并为集合。"""
    return {origin for record in records for origin in record.gt_data}


def single_output_aliases(evidence: OracleReceiptEvidence) -> tuple[str, ...]:
    """读取零个或恰好一组 Tool 输出 alias。"""
    if not evidence.output_aliases:
        return ()
    if len(evidence.output_aliases) != 1:
        raise OracleInvariantError(
            "tool_output",
            f"动作 {evidence.action_id} 的输出 alias 数量不一致",
        )
    return evidence.output_aliases[0]
