"""T16-B 双 Fake Slot 的逐链执行。"""

from dataclasses import dataclass
from decimal import Decimal
from typing import assert_never

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.dry_run_errors import DryRunDesignError, DryRunDesignReason
from skillflow.experiment.t16.dry_run_records import (
    A1_PRESERVED_FIELDS,
    DryRunInterventionAudit,
    DryRunTrialRecord,
    FakeModelSlot,
    SessionEffectObservation,
    T16BDryRunConfig,
)
from skillflow.experiment.t16.matrix import MatrixKind, T16Matrix, TrialSpec
from skillflow.experiment.t16.preregistration_models import (
    IndependentFactor,
    PairRole,
    T16Condition,
    T16Intervention,
    T16Preregistration,
)
from skillflow.experiment.t16.provider import (
    FakeProvider,
    ProviderCallResult,
    ProviderRequest,
    TokenUsage,
)
from skillflow.experiment.t16.trial import (
    ProvenanceRecord,
    ProvenanceStatus,
    TrialOutcome,
    TrialResult,
)
from skillflow.models.matrix_design import HiaaCell


@dataclass(frozen=True, slots=True)
class _ExecutionContext:
    spec: TrialSpec
    condition: T16Condition
    slot: FakeModelSlot
    max_agent_turns: int


@dataclass(frozen=True, slots=True)
class _InvocationAggregate:
    usage: TokenUsage
    api_call_count: int
    latency_ms: int
    estimated_cost_usd: Decimal
    budget: BudgetLedger


@dataclass(frozen=True, slots=True)
class _FakeBehavior:
    target_effect_requested: bool
    target_effect_executed: bool


def execute_fake_matrix(
    registration: T16Preregistration,
    matrix: T16Matrix,
    config: T16BDryRunConfig,
) -> tuple[DryRunTrialRecord, ...]:
    """用两个逻辑 Fake Slot 完整执行单模型 360 链矩阵。"""
    if matrix.kind is not MatrixKind.MODEL1:
        raise DryRunDesignError(DryRunDesignReason.WRONG_MATRIX)
    conditions = {item.condition_id: item for item in registration.conditions}
    ledger = BudgetLedger(config.budget)
    records: list[DryRunTrialRecord] = []
    for slot in config.slots:
        for spec in matrix.trials:
            condition = conditions.get(spec.condition_id)
            if condition is None:
                raise DryRunDesignError(
                    DryRunDesignReason.UNKNOWN_CONDITION,
                    spec.condition_id,
                )
            context = _ExecutionContext(
                spec=spec,
                condition=condition,
                slot=slot,
                max_agent_turns=config.budget.max_agent_turns,
            )
            record, ledger = _execute_trial(context, ledger.begin_run())
            records.append(record)
    return tuple(records)


def _execute_trial(
    context: _ExecutionContext,
    budget: BudgetLedger,
) -> tuple[DryRunTrialRecord, BudgetLedger]:
    behavior = _derive_fake_behavior(context.condition)
    aggregate = _invoke_fake(context, budget)
    observations = _session_observations(context, behavior)
    receipt_id = next(
        (item.receipt_id for item in observations if item.receipt_id is not None),
        None,
    )
    if behavior.target_effect_executed and receipt_id is None:
        receipt_id = f"receipt-{context.slot.slot_id}-{context.spec.trial_id}"
    outcome = (
        TrialOutcome.HARM
        if behavior.target_effect_executed
        else TrialOutcome.COMPLETED_WITHOUT_HARM
    )
    result = TrialResult(
        trial_id=f"{context.slot.slot_id}--{context.spec.trial_id}",
        scenario=context.spec.scenario,
        condition_id=context.spec.condition_id,
        semantic_instance_id=context.spec.semantic_instance_id,
        pair_id=context.spec.pair_id,
        repeat_index=context.spec.repeat_index,
        provider=context.slot.provider.kind,
        model_id=context.slot.provider.model_id,
        model_revision=context.slot.provider.model_revision,
        temperature=context.slot.provider.temperature,
        reasoning_effort=context.slot.provider.reasoning_effort,
        max_agent_turns=context.max_agent_turns,
        task_success=True,
        target_effect_requested=behavior.target_effect_requested,
        target_effect_executed=behavior.target_effect_executed,
        receipt_id=receipt_id,
        token_usage=aggregate.usage,
        api_call_count=aggregate.api_call_count,
        latency_ms=aggregate.latency_ms,
        estimated_cost_usd=aggregate.estimated_cost_usd,
        provenance=ProvenanceRecord(
            status=ProvenanceStatus.NOT_AVAILABLE,
            reason="Fake Provider 没有平台 Hook；不得把缺失来源记为安全结果 0",
        ),
        outcome=outcome,
    )
    audit = _intervention_audit(context.condition)
    record = DryRunTrialRecord(
        slot_id=context.slot.slot_id,
        matrix_trial_id=context.spec.trial_id,
        pair_role=context.condition.pair_role,
        independent_factor=context.condition.independent_factor,
        hiaa_cell=context.condition.hiaa_cell,
        harm_selector=context.condition.harm_selector,
        session_observations=observations,
        intervention_audit=audit,
        result=result,
    )
    return record, aggregate.budget


def _invoke_fake(context: _ExecutionContext, budget: BudgetLedger) -> _InvocationAggregate:
    response = _fake_response(context.condition.independent_factor)
    is_memory = context.condition.independent_factor is IndependentFactor.MEMORY_SEMANTICS
    call_count = 3 if is_memory else 1
    total_usage = TokenUsage(
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=0,
        reasoning_tokens=0,
    )
    total_latency = 0
    total_cost = Decimal(0)
    current = budget
    for _call_index in range(call_count):
        invocation = FakeProvider(context.slot.provider, response).invoke(
            ProviderRequest(
                input_text=context.spec.task_prompt,
                estimated_input_tokens=response.token_usage.input_tokens,
                cached_input_tokens=response.token_usage.cached_input_tokens,
                max_output_tokens=(
                    response.token_usage.output_tokens + response.token_usage.reasoning_tokens
                ),
            ),
            current,
        )
        total_usage = _add_usage(total_usage, invocation.result.token_usage)
        total_latency += invocation.result.latency_ms
        total_cost += invocation.estimated_cost_usd
        current = invocation.budget
    return _InvocationAggregate(total_usage, call_count, total_latency, total_cost, current)


def _fake_response(factor: IndependentFactor) -> ProviderCallResult:
    match factor:
        case IndependentFactor.MEMORY_SEMANTICS:
            usage = TokenUsage(
                input_tokens=240,
                cached_input_tokens=60,
                output_tokens=80,
                reasoning_tokens=20,
            )
            latency = 3
        case (
            IndependentFactor.NONE
            | IndependentFactor.SKILL_SEMANTICS
            | IndependentFactor.AUTHORIZATION_SOURCE
        ):
            usage = TokenUsage(
                input_tokens=120,
                cached_input_tokens=20,
                output_tokens=40,
                reasoning_tokens=10,
            )
            latency = 1
        case unreachable:
            assert_never(unreachable)
    return ProviderCallResult(
        output_text="fake-operational-response",
        token_usage=usage,
        latency_ms=latency,
    )


def _derive_fake_behavior(condition: T16Condition) -> _FakeBehavior:
    match condition.independent_factor:
        case IndependentFactor.NONE:
            active = False
        case IndependentFactor.SKILL_SEMANTICS:
            active = condition.pair_role is PairRole.TARGET and condition.hiaa_cell is HiaaCell.P11
        case IndependentFactor.MEMORY_SEMANTICS | IndependentFactor.AUTHORIZATION_SOURCE:
            active = condition.pair_role is PairRole.TARGET
        case unreachable:
            assert_never(unreachable)
    return _FakeBehavior(target_effect_requested=active, target_effect_executed=active)


def _session_observations(
    context: _ExecutionContext,
    behavior: _FakeBehavior,
) -> tuple[SessionEffectObservation, ...]:
    return tuple(
        SessionEffectObservation(
            session_index=session,
            target_effect_requested=behavior.target_effect_requested,
            target_effect_executed=behavior.target_effect_executed,
            receipt_id=(
                f"receipt-{context.slot.slot_id}-{context.spec.trial_id}-s{session}"
                if behavior.target_effect_executed
                else None
            ),
        )
        for session in context.condition.observation_sessions
    )


def _intervention_audit(condition: T16Condition) -> DryRunInterventionAudit | None:
    if condition.intervention is not T16Intervention.NEUTRALIZE_AUTHORIZATION_CLAIM:
        return None
    return DryRunInterventionAudit(
        intervention=condition.intervention,
        removed_fields=("authorization_claim",),
        preserved_fields=A1_PRESERVED_FIELDS,
    )


def _add_usage(left: TokenUsage, right: TokenUsage) -> TokenUsage:
    return TokenUsage(
        input_tokens=left.input_tokens + right.input_tokens,
        cached_input_tokens=left.cached_input_tokens + right.cached_input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        reasoning_tokens=left.reasoning_tokens + right.reasoning_tokens,
    )
