"""不含模型正文的标准逐条数据；删除重复投影而不删除事实。"""

from typing import Literal, Self

from pydantic import Field

from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.experiment.t17.minimal.task_models import NormalTaskEvidence
from skillflow.experiment.t17.v2.api_models import ApiUsageEvent
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.frozen import FrozenFile
from skillflow.experiment.t17.v2.portable import recompute_core
from skillflow.experiment.t17.v2.portable_models import PortableCore, PortableCoreInputs
from skillflow.experiment.t17.v2.run_models import (
    CoreTerminal,
    ReplayProof,
    ReplayTerminal,
    TerminalStatus,
    UnitIdentity,
    UnitUsage,
)
from skillflow.experiment.t17.v2.runtime_models import DecisionFact, ExecutionIssue
from skillflow.instrumentation.tool_receipt import ToolReceiptDraft
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import EffectRecord
from skillflow.models.provenance import Artifact
from skillflow.oracle.models import OracleArtifactTrace


class CoreRow(StrictModel):
    """原始结构化输入足以复算完整投影，投影本身只保存哈希。"""

    schema_version: Literal["2.0"] = "2.0"
    identity: UnitIdentity
    status: TerminalStatus
    reason: NonEmptyStr | None
    run_id: NonEmptyStr | None
    data: PortableCoreInputs | None
    proof_sha256: Sha256 | None
    decisions: tuple[DecisionFact, ...]
    issues: tuple[ExecutionIssue, ...]
    usage: UnitUsage
    wall_latency_ms: float
    raw_files: dict[NonEmptyStr, FrozenFile]

    @classmethod
    def from_terminal(cls, record: CoreTerminal) -> Self:
        """仅省去可重建投影，不丢弃失败用量或原始文件清单。"""
        data = None if record.data is None else record.data.model_dump(exclude={"proof"})
        return cls.model_validate(
            {
                **record.model_dump(exclude={"data"}),
                "data": data,
                "proof_sha256": None if record.data is None else model_digest(record.data.proof),
            }
        )

    def restore(self) -> CoreTerminal:
        """复算值与保存承诺不同，拒绝装载。"""
        data = None
        if self.data is not None:
            proof = recompute_core(self.data)
            if model_digest(proof) != self.proof_sha256:
                raise ValueError("v2_dataset_core_proof_drift")
            data = PortableCore(**self.data.model_dump(), proof=proof)
        elif self.proof_sha256 is not None:
            raise ValueError("v2_dataset_proof_without_facts")
        return CoreTerminal.model_validate(
            {**self.model_dump(exclude={"data", "proof_sha256"}), "data": data}
        )


class ReplayRow(StrictModel):
    """不存在目标时引用同核心的事实哈希，不重复复制整个核心运行。"""

    schema_version: Literal["2.0"] = "2.0"
    identity: UnitIdentity
    source_core_run_id: NonEmptyStr | None
    target_alias: NonEmptyStr
    status: TerminalStatus
    reason: NonEmptyStr | None
    proof: ReplayProof | None
    absent_source_sha256: Sha256 | None
    decisions: tuple[DecisionFact, ...]
    issues: tuple[ExecutionIssue, ...]
    usage: UnitUsage
    raw_files: dict[NonEmptyStr, FrozenFile]

    @classmethod
    def from_terminal(cls, record: ReplayTerminal) -> Self:
        """回放双分支原始事实保留，不能只发布因果差标签。"""
        return cls.model_validate(
            {
                **record.model_dump(exclude={"absent_source"}),
                "absent_source_sha256": None
                if record.absent_source is None
                else model_digest(record.absent_source),
            }
        )

    def restore(self, core: CoreTerminal) -> ReplayTerminal:
        """缺失证明只可来自相同核心，不能跨运行借用。"""
        source = None
        if self.absent_source_sha256 is not None:
            if core.data is None or model_digest(core.data.facts) != self.absent_source_sha256:
                raise ValueError("v2_dataset_absence_source_drift")
            source = core.data.facts
        return ReplayTerminal.model_validate(
            {**self.model_dump(exclude={"absent_source_sha256"}), "absent_source": source}
        )


class TaskEvidenceRow(StrictModel):
    """逐核心任务的独立正常及安全成功判定。"""

    identity: UnitIdentity
    run_id: NonEmptyStr
    session_ids: tuple[NonEmptyStr, ...]
    evidence: NormalTaskEvidence


class EffectReceiptRow(StrictModel):
    """逐操作保留事件绑定及回执；分支前缀不能再次当独立效果计数。"""

    identity: UnitIdentity
    run_id: NonEmptyStr
    session_id: NonEmptyStr
    branch: Literal["core", "original", "neutral"]
    in_replay_prefix: bool
    effect: EffectRecord
    receipt: ToolReceiptDraft


class ProvenanceRow(StrictModel):
    """按输出值保存其观察父边与真实父边，可直接比较丢失的来源。"""

    identity: UnitIdentity
    run_id: NonEmptyStr
    session_id: NonEmptyStr
    artifact: Artifact
    oracle: OracleArtifactTrace | None = None


class ApiUsageRow(StrictModel):
    """每次请求及响应都能追溯到完整任务、技能和模型身份。"""

    identity: UnitIdentity
    event: ApiUsageEvent


class HashManifest(StrictModel):
    """自文件不能自哈希；外层交付清单再登记本文件哈希。"""

    schema_version: Literal["2.0"] = "2.0"
    self_excluded: Literal["sha256-manifest.json"] = "sha256-manifest.json"
    files: dict[NonEmptyStr, FrozenFile] = Field(default_factory=dict)
