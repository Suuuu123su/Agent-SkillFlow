"""无模型正文、无宿主路径的逐运行原始事实与可复算投影。"""

from typing import Literal

from skillflow.analysis.facts import RunReportMetadata
from skillflow.experiment.t17.contracts import HookCapability
from skillflow.experiment.t17.minimal.contracts import NormalTaskContract
from skillflow.experiment.t17.minimal.task_models import NormalTaskEvidence
from skillflow.experiment.t17.observation_models import ReferenceObservationSnapshot
from skillflow.experiment.t17.v2.claim_models import ClaimActionSpec
from skillflow.instrumentation.tool_receipt import ToolReceiptDraft
from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import EffectRecord
from skillflow.models.events import DecisionRecord, SecurityEvent
from skillflow.models.provenance import Artifact
from skillflow.models.reports import RunRiskReport
from skillflow.models.scenario import Scenario
from skillflow.oracle.models import OracleTraceRecord
from skillflow.store.event_store import RevocationRecord
from skillflow.trace.observed import ObservedTraceRecord


class PortableRun(StrictModel):
    """从一个运行的事件库和回执恢复；不含 Blob 内容。"""

    schema_version: Literal["2.0"] = "2.0"
    run_id: NonEmptyStr
    events: tuple[SecurityEvent, ...]
    artifacts: tuple[Artifact, ...]
    decisions: tuple[DecisionRecord, ...]
    effects: tuple[EffectRecord, ...]
    grants: tuple[AuthorizationGrant, ...]
    revocations: tuple[RevocationRecord, ...]
    receipts: tuple[ToolReceiptDraft, ...]


class CoreProof(StrictModel):
    """完全由脱敏事件、来源真值和任务规则计算，不读汇总百分比。"""

    task: NormalTaskEvidence
    runtime: ReferenceObservationSnapshot
    hooks: tuple[HookCapability, ...]
    report: RunRiskReport
    step_event_ids: tuple[NonEmptyStr, ...]


class PortableCoreInputs(StrictModel):
    """去除提示和资产正文后的复算输入，不能拿来发起新的实验。"""

    schema_version: Literal["2.0"] = "2.0"
    facts: PortableRun
    analysis_definition: Scenario
    task_contract: NormalTaskContract
    metadata: RunReportMetadata
    artifact_ids_by_alias: dict[NonEmptyStr, NonEmptyStr]
    observed: tuple[ObservedTraceRecord, ...]
    oracle: tuple[OracleTraceRecord, ...]
    claim_bindings: tuple[ClaimActionSpec, ...] = ()


class PortableCore(PortableCoreInputs):
    """输入和已算结果同时保存，离线必须能逐项复算相等。"""

    proof: CoreProof
