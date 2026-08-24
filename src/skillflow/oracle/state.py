"""Oracle GT_data 的机械传播状态。"""

from collections.abc import Iterable
from typing import assert_never

from skillflow.models.scenario_parts import AssetSpec
from skillflow.models.tool_calls import (
    HttpSendArgs,
    ReadFileArgs,
    ReadMemoryArgs,
    ShellExecArgs,
    WriteMemoryArgs,
)
from skillflow.oracle.effects import OracleActionSemantics
from skillflow.oracle.errors import OracleInvariantError
from skillflow.oracle.models import (
    OracleActionPlan,
    OracleArtifactTrace,
    OracleAttemptEvidence,
    OracleInvocationEvidence,
    OracleReceiptEvidence,
)
from skillflow.trace.contracts import ParentRelation, TraceParent, TraceValueType


class OracleDataState:
    """只由声明动作和稳定运行 ID 更新的独立值状态。"""

    def __init__(self, run_id: str, assets: tuple[AssetSpec, ...]) -> None:
        """在执行前把 Scenario asset 注册为稳定根值。"""
        self._run_id = run_id
        self._records: list[OracleArtifactTrace] = []
        self._by_id: dict[str, OracleArtifactTrace] = {}
        self._assets_by_resource: dict[str, str] = {}
        self._asset_origins: dict[str, str] = {}
        self._memory: dict[str, str] = {}
        for asset in assets:
            resource = _workspace_resource(asset)
            artifact_id = f"asset:{asset.id}"
            self._assets_by_resource[resource] = artifact_id
            self._asset_origins[asset.id] = resource
            self._add(
                OracleArtifactTrace(
                    run_id=run_id,
                    artifact_id=artifact_id,
                    value_type=TraceValueType.ASSET,
                    aliases=(artifact_id,),
                    gt_data=(resource,),
                    parents=(),
                )
            )

    @property
    def records(self) -> tuple[OracleArtifactTrace, ...]:
        """返回当前已机械生成的 Oracle 值序列。"""
        return tuple(self._records)

    def require(self, artifact_id: str) -> OracleArtifactTrace:
        """只从 Oracle 自己的状态读取父值，绝不回退到 Observed。"""
        try:
            return self._by_id[artifact_id]
        except KeyError as error:
            raise OracleInvariantError(
                "resolve_parent",
                f"Oracle 父值不存在：{artifact_id}",
            ) from error

    def asset_origin(self, asset_id: str) -> str:
        """把 Scenario asset alias 解析为规范运行资源来源。"""
        try:
            return self._asset_origins[asset_id]
        except KeyError as error:
            raise OracleInvariantError(
                "resolve_asset_origin",
                f"Scenario asset 不存在：{asset_id}",
            ) from error

    def record_argument(
        self,
        skill_id: str,
        semantics: OracleActionSemantics,
        evidence: OracleAttemptEvidence,
    ) -> None:
        """从脚本动作的数据父值生成 Tool argument 真值。"""
        parents = tuple(
            TraceParent(parent_id=item, relation=ParentRelation.INVOKE)
            for item in semantics.source_artifact_ids
        )
        origins = (
            _origins(self.require(item) for item in semantics.source_artifact_ids)
            if semantics.source_artifact_ids
            else (skill_id,)
        )
        self._add(
            OracleArtifactTrace(
                run_id=self._run_id,
                artifact_id=evidence.argument_artifact_id,
                value_type=TraceValueType.TOOL_ARG,
                gt_data=origins,
                parents=parents,
            )
        )

    def record_outputs(
        self,
        action: OracleActionPlan,
        evidence: OracleReceiptEvidence,
    ) -> tuple[str, ...]:
        """按封闭动作类型传播 File/Memory 输出的 GT_data。"""
        arguments = action.arguments
        match arguments:
            case ReadFileArgs(resource=resource):
                output_id = self._single_output(evidence)
                try:
                    parent_id = self._assets_by_resource[resource.root]
                except KeyError as error:
                    raise OracleInvariantError(
                        "file_load",
                        f"read_file 未引用 Scenario asset：{resource.root}",
                    ) from error
                self._copy_value(output_id, TraceValueType.FILE, parent_id, ParentRelation.LOAD)
                return (output_id,)
            case WriteMemoryArgs(key=key, source_artifact_id=source_id):
                output_id = self._single_output(evidence)
                self._copy_value(
                    output_id,
                    TraceValueType.MEMORY,
                    source_id,
                    ParentRelation.WRITE,
                )
                self._memory[key] = output_id
                return (output_id,)
            case ReadMemoryArgs(key=key):
                output_id = self._single_output(evidence)
                try:
                    parent_id = self._memory[key]
                except KeyError as error:
                    raise OracleInvariantError(
                        "memory_load",
                        f"Memory 真值头不存在：{key}",
                    ) from error
                self._copy_value(
                    output_id,
                    TraceValueType.MEMORY,
                    parent_id,
                    ParentRelation.LOAD,
                )
                return (output_id,)
            case HttpSendArgs() | ShellExecArgs():
                if evidence.output_artifact_ids:
                    raise OracleInvariantError(
                        "effect_output",
                        f"{arguments.kind.value} 不应生成值 Artifact",
                    )
                return ()
            case _ as unreachable:
                assert_never(unreachable)

    def record_receipt(
        self,
        skill_id: str,
        evidence: OracleReceiptEvidence,
        output_ids: tuple[str, ...],
    ) -> None:
        """记录 Receipt 元数据值及其调用父关系。"""
        parent_ids = (evidence.argument_artifact_id, *output_ids)
        self._add(
            OracleArtifactTrace(
                run_id=self._run_id,
                artifact_id=evidence.receipt_artifact_id,
                value_type=TraceValueType.TOOL_RETURN,
                gt_data=(skill_id,),
                parents=tuple(
                    TraceParent(parent_id=item, relation=ParentRelation.INVOKE)
                    for item in parent_ids
                ),
            )
        )

    def record_skill_output(
        self,
        evidence: OracleInvocationEvidence,
        action_output_ids: tuple[str, ...],
    ) -> None:
        """把显式输入与 Tool 数据输出机械汇入 Skill return。"""
        parent_ids = tuple(dict.fromkeys((*evidence.input_artifact_ids, *action_output_ids)))
        parent_records = tuple(self.require(item) for item in parent_ids)
        origins = tuple(sorted({evidence.skill_id, *_origins_set(parent_records)}))
        self._add(
            OracleArtifactTrace(
                run_id=self._run_id,
                artifact_id=evidence.output_artifact_id,
                value_type=TraceValueType.SKILL_OUTPUT,
                aliases=evidence.output_aliases,
                gt_data=origins,
                parents=tuple(
                    TraceParent(parent_id=item, relation=ParentRelation.INVOKE)
                    for item in parent_ids
                ),
            )
        )

    def effect_data(
        self,
        evidence: OracleReceiptEvidence,
        output_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        """从 Tool argument 与真实输出汇总 Effect 的数据来源。"""
        records = (
            self.require(evidence.argument_artifact_id),
            *(self.require(item) for item in output_ids),
        )
        return _origins(records)

    def _copy_value(
        self,
        artifact_id: str,
        value_type: TraceValueType,
        parent_id: str,
        relation: ParentRelation,
    ) -> None:
        parent = self.require(parent_id)
        self._add(
            OracleArtifactTrace(
                run_id=self._run_id,
                artifact_id=artifact_id,
                value_type=value_type,
                gt_data=parent.gt_data,
                parents=(TraceParent(parent_id=parent_id, relation=relation),),
            )
        )

    def _single_output(self, evidence: OracleReceiptEvidence) -> str:
        if len(evidence.output_artifact_ids) != 1:
            raise OracleInvariantError(
                "tool_output",
                f"动作 {evidence.action_id} 要求恰好一个输出 Artifact",
            )
        return evidence.output_artifact_ids[0]

    def _add(self, record: OracleArtifactTrace) -> None:
        if record.artifact_id in self._by_id:
            raise OracleInvariantError(
                "stable_id",
                f"Oracle Artifact ID 重复：{record.artifact_id}",
            )
        self._by_id[record.artifact_id] = record
        self._records.append(record)


def _workspace_resource(asset: AssetSpec) -> str:
    prefix = "fixture://"
    if not asset.uri.root.startswith(prefix):
        raise OracleInvariantError(
            "asset_projection",
            f"T06 asset 必须使用 fixture://：{asset.uri.root}",
        )
    return f"workspace:/{asset.uri.root.removeprefix(prefix)}"


def _origins(records: Iterable[OracleArtifactTrace]) -> tuple[str, ...]:
    return tuple(sorted(_origins_set(records)))


def _origins_set(records: Iterable[OracleArtifactTrace]) -> set[str]:
    return {origin for record in records for origin in record.gt_data}
