"""T18 专属阶段与逐核心记录，旧 T17 证据模型只作为不可变事实载荷。"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from skillflow.defense.provider import DefenseTrace
from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.experiment.t17.v2.portable_models import PortableCore
from skillflow.experiment.t17.v2.runtime_models import DecisionFact, ExecutionIssue
from skillflow.experiment.t18.matrix import CoreCell, Domain
from skillflow.models.base import NonEmptyStr, StrictModel


class LocalPhase(StrictModel):
    """同协议域的固定调度；每条记录都必须绑定此合同。"""

    schema_version: Literal["18.0"] = "18.0"
    protocol_id: Literal["t18-local-hiaa-v1"] = "t18-local-hiaa-v1"
    domain: Domain
    matrix_sha256: Sha256
    catalog_sha256: Sha256
    preregistration_sha256: Sha256
    runtime_sources: dict[NonEmptyStr, Sha256]
    scheduled_core: Annotated[int, Field(gt=0)]
    max_replay_pairs: Annotated[int, Field(ge=0)]
    paid_api_calls: Literal[0] = 0


class LocalCore(StrictModel):
    """模型失败是完成的任务；证据或基础设施失败单独终态化。"""

    schema_version: Literal["18.0"] = "18.0"
    phase_contract_sha256: Sha256
    domain: Domain
    cell: CoreCell
    run_id: NonEmptyStr
    status: Literal["completed", "infrastructure_invalid", "evidence_binding_failure"]
    failure_reason: NonEmptyStr | None = None
    data: PortableCore | None = None
    traces: tuple[DefenseTrace, ...] = ()
    decisions: tuple[DecisionFact, ...] = ()
    issues: tuple[ExecutionIssue, ...] = ()
    replay_pair_ids: tuple[NonEmptyStr, ...] = ()
    latency_ms: Annotated[float, Field(ge=0)]

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        """任何跨运行证据或授权洗白都不能进入已完成记录。"""
        if self.status == "completed":
            if (
                self.data is None
                or self.data.facts.run_id != self.run_id
                or self.failure_reason is not None
            ):
                raise ValueError("t18_core_terminal_binding")
            decisions = {d.request_event_id: d for d in self.data.facts.decisions}
            if set(decisions) != {t.request_event_id for t in self.traces}:
                raise ValueError("t18_defense_trace_coverage")
            for trace in self.traces:
                decision = decisions[trace.request_event_id]
                if (
                    trace.run_id != self.run_id
                    or trace.base_authorized != trace.final_authorized
                    or trace.final_authorized != decision.authorized
                    or trace.final_executed != decision.executed
                ):
                    raise ValueError("t18_defense_authorization_binding")
        elif self.failure_reason is None:
            raise ValueError("t18_core_failure_reason_missing")
        return self
