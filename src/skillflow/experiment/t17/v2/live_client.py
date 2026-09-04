"""第二版预算批准后的真实模型入口，密钥只保存在同一监督进程内。"""

import json
from pathlib import Path

from pydantic import SecretStr, ValidationError

from skillflow.experiment.t16.budget import BudgetExceededError, BudgetSettlementError
from skillflow.experiment.t16.live_agent_calls import CallPersistence, invoke_with_retry
from skillflow.experiment.t16.openai_output_schemas import ResponseOutputContract
from skillflow.experiment.t16.openai_response_models import OpenAIResponsesCall
from skillflow.experiment.t16.openai_responses import (
    OpenAIResponsesClient,
    OpenAIResponsesTurn,
    ResponsesTransport,
)
from skillflow.experiment.t17.reference_backend import ReferenceModelDecision, ReferenceModelRequest
from skillflow.experiment.t17.v2.api_models import (
    CallIdentity,
    V2BudgetExhaustedError,
    V2LiveConfig,
    V2ProviderFailureError,
    V2RevisionDriftError,
    V2UsageUnavailableError,
)
from skillflow.experiment.t17.v2.audited_transport import (
    AuditedResponsesTransport,
    UsagePreservingClient,
)
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.journal import V2UsageJournal
from skillflow.experiment.t17.v2.prompt_contract import input_items
from skillflow.experiment.t17.v2.run_models import PhaseContract, UnitUsage
from skillflow.experiment.t17.v2.runtime_models import ModelBehavior, ModelOutcomeError


class V2LiveClient:
    """不在构造时请求网络；完整阶段合同和追加日志就绪后才能调用。"""

    def __init__(
        self, config: V2LiveConfig, secret: SecretStr, transport: ResponsesTransport
    ) -> None:
        """保持密钥不进入环境变量、参数、报告或对象表示。"""
        self.config = config
        self._secret, self._transport = secret, transport
        self._journal: V2UsageJournal | None = None
        self._client: UsagePreservingClient | None = None
        self._revision_drift = False

    def __repr__(self) -> str:
        """即使调试也不显示密钥或请求内容。"""
        return "V2LiveClient(secret=**********)"

    def authorized_for(self, matrix_sha256: str) -> bool:
        """总预算授权拆分出的阶段不能用于其他矩阵。"""
        return self.config.budget.allow_live and self.config.matrix_sha256 == matrix_sha256

    def open_phase(self, output: Path, phase: PhaseContract) -> None:
        """请求前将用量哈希链绑定到已保存的阶段合同。"""
        if not self.authorized_for(phase.matrix_sha256):
            raise ValueError("v2_phase_not_authorized")
        self.open_journal(output / "api-usage.jsonl", model_digest(phase))

    def open_journal(self, path: Path, phase_sha256: str) -> None:
        """日志只可打开一次，恢复必须新建尝试，不能回填失败记录。"""
        if self._journal is not None:
            raise ValueError("v2_journal_already_open")
        journal = V2UsageJournal(path, self.config, phase_sha256)
        transport = AuditedResponsesTransport(self._transport, journal, self._secret)
        self._journal = journal
        self._client = UsagePreservingClient(
            OpenAIResponsesClient(self._secret, transport, self.config.endpoint), journal
        )

    def begin_unit(self, unit_id: str) -> None:
        """重置单任务预算，但不清空总预算和失败尝试。"""
        self._ready().begin_unit(unit_id)

    def bind_call(self, identity: CallIdentity) -> None:
        """运行时提供真实身份，模型无权覆盖。"""
        self._ready().call = identity

    def unit_usage(self) -> UnitUsage:
        """仅返回已经同步落盘的用量。"""
        return self._ready().usage()

    def decide(self, request: ReferenceModelRequest) -> ReferenceModelDecision:
        """有限重试只适用于提供方瞬态错误，不适用于任何模型结果。"""
        if self._revision_drift:
            raise V2RevisionDriftError("v2_revision_drift_stopped")
        journal = self._ready()
        client = self._client
        if client is None or journal.call is None or journal.unit_id == "unbound":
            raise ValueError("v2_call_context_not_bound")
        items = input_items(request)
        if self.config.provider.model_id == "deepseek-v4-flash":
            # DeepSeek 将 developer 降为 user；只映射角色，冻结正文不变。
            items = ({**items[0], "role": "system"}, *items[1:])
        call = OpenAIResponsesCall(
            model=self.config.provider.model_id,
            temperature=None,
            reasoning_effort=self.config.provider.reasoning_effort,
            max_output_tokens=self.config.budget.max_output_tokens_per_turn,
            input_items=items,
            output_contract=ResponseOutputContract.REFERENCE_DECISION_V4,
            prompt_cache_mode=self.config.prompt_cache_mode,
        )
        if (
            len(json.dumps(call.payload(), ensure_ascii=False, separators=(",", ":")).encode())
            > self.config.max_input_bytes
        ):
            raise V2BudgetExhaustedError("input_bytes")
        turn = self._execute(call, client, journal)
        if turn.model_revision != self.config.provider.model_revision:
            self._revision_drift = True
            journal.append("revision_drift", reason="model_revision_changed")
            raise V2RevisionDriftError("v2_model_revision_changed")
        if turn.refusal:
            self._model_failure("refusal")
        if turn.status != "completed" or turn.function_calls:
            self._model_failure("schema_rejection")
        try:
            return ReferenceModelDecision.model_validate_json(turn.output_text)
        except ValidationError as error:
            journal.append("model_failure", reason="schema_rejection")
            raise ModelOutcomeError("schema_rejection") from error

    def _execute(
        self, call: OpenAIResponsesCall, client: UsagePreservingClient, journal: V2UsageJournal
    ) -> OpenAIResponsesTurn:
        try:
            executed = invoke_with_retry(
                call, self.config, client, journal.ledger, CallPersistence(usage=journal)
            )
        except BudgetExceededError as error:
            raise V2BudgetExhaustedError(error.limit.value) from error
        except BudgetSettlementError as error:
            raise V2UsageUnavailableError("v2_response_cost_exceeds_reservation") from error
        journal.ledger = executed.budget
        if executed.turn is None:
            if journal.received is not None:
                if executed.failure == "schema_rejection" and self._known_empty_overrun(
                    call, journal
                ):
                    self._model_failure("schema_rejection")
                raise V2UsageUnavailableError("v2_usage_exceeds_frozen_bound")
            raise V2ProviderFailureError(executed.failure or "provider_error")
        return executed.turn

    def _known_empty_overrun(self, call: OpenAIResponsesCall, journal: V2UsageJournal) -> bool:
        """用户批准：完整用量、原金额预留内的 DeepSeek 超限空响应仍为模型失败。"""
        event = journal.received
        if (
            self.config.provider.model_id != "deepseek-v4-flash"
            or event is None
            or event.usage is None
            or event.estimated_cost_usd is None
            or event.model_revision != self.config.provider.model_revision
            or event.response_status != "incomplete"
            or event.usage.output_tokens != 0
            or event.usage.reasoning_tokens <= call.max_output_tokens
        ):
            return False
        payload = json.dumps(call.payload(), ensure_ascii=False, separators=(",", ":"))
        if event.usage.input_tokens > len(payload.encode()) + 256:
            return False
        attempt = next(
            e
            for e in reversed(journal.events)
            if e.event_type == "attempt" and e.attempt_index == event.attempt_index
        )
        previous = journal.events[attempt.sequence - 2]
        reserved = attempt.total_reserved_usd - previous.total_reserved_usd
        # 不释放未结算预留，不提高请求 token 或金额门，也不重试该响应。
        return event.estimated_cost_usd <= reserved

    def _ready(self) -> V2UsageJournal:
        if self._journal is None:
            raise ValueError("v2_journal_not_open")
        return self._journal

    def _model_failure(self, behavior: ModelBehavior) -> None:
        self._ready().append("model_failure", reason=behavior)
        raise ModelOutcomeError(behavior)
