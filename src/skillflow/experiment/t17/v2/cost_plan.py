"""完成离线准备后生成一次总预算申请，不联网核价、不读取凭据。"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from skillflow.experiment.t16.budget import BudgetConfig
from skillflow.experiment.t16.provider import ProviderRequest, TokenUsage, estimate_reservation_cost
from skillflow.experiment.t17.live_matrix import T17LiveStage, load_live_preregistration
from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.config_models import V2Matrix
from skillflow.experiment.t17.v2.cost_history import historical_usage, projected_response_costs
from skillflow.experiment.t17.v2.cost_models import CostPlan, StageCost
from skillflow.experiment.t17.v2.formal_scope import require_full_t17
from skillflow.experiment.t17.v2.frozen import file_digest
from skillflow.experiment.t17.v2.readiness import offline_evidence
from skillflow.experiment.t17.v2.static_protocol import verify_protocol
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import StepAction
from skillflow.validation import validate_yaml_document

HISTORY = "runs/t17-live-20260902-05/canary/attempt-01/actual-usage-journal.jsonl"


def graph_call_counts(root: Path, matrix: V2Matrix) -> tuple[int, ...]:
    """根据声明式步骤计算每个核心和重放后缀的最大正常调用数。"""
    counts = []
    for trial in matrix.trials:
        scenario = validate_yaml_document(root / trial.configuration.scenario.root, Scenario)
        steps = tuple(step for session in scenario.sessions for step in session.steps)
        counts.append(sum(step.action is StepAction.INVOKE_SKILL for step in steps))
        for alias in trial.replay_pair_ids:
            position = next(
                index
                for index, step in enumerate(steps)
                if alias
                in {a.alias for a in step.outputs} | {a.alias.alias for a in step.tool_outputs}
            )
            counts.append(
                2 * sum(step.action is StepAction.INVOKE_SKILL for step in steps[position + 1 :])
            )
    return tuple(counts)


def stage_cost(
    root: Path, matrix: V2Matrix, budget: BudgetConfig, samples: tuple[TokenUsage, ...]
) -> StageCost:
    """最坏 Token 与申请上限分别列出，预算不足会停止而非无限消费。"""
    counts = graph_call_counts(root, matrix)
    attempts = sum(
        min(budget.max_agent_turns, count + budget.max_retries) if count else 0 for count in counts
    )
    mean, p95 = projected_response_costs(matrix.provider.pricing, samples)
    worst = ProviderRequest(
        input_text="planning-only",
        estimated_input_tokens=100256,
        max_output_tokens=budget.max_output_tokens_per_turn,
    )
    return StageCost(
        stage=matrix.stage,
        matrix_sha256=model_digest(matrix),
        model_id=matrix.provider.model_id,
        scheduled_core=matrix.scheduled_core_trials,
        scheduled_replay=matrix.scheduled_replay_pairs,
        no_failure_api_calls=sum(counts),
        max_network_attempts=attempts,
        worst_input_tokens=attempts * worst.estimated_input_tokens,
        worst_output_including_reasoning_tokens=attempts * worst.max_output_tokens,
        expected_estimated_usd=mean * sum(counts),
        historical_p95_projected_usd=p95 * sum(counts),
        uncapped_token_upper_cost_usd=estimate_reservation_cost(matrix.provider, worst) * attempts,
        budget=budget,
        rates=matrix.provider.pricing,
        rate_source="https://developers.openai.com/api/docs/models/"
        + (
            "gpt-5.5"
            if matrix.stage in {T17LiveStage.MODEL2, T17LiveStage.MODEL2_CANARY}
            else "gpt-5.6-luna"
        ),
    )


def build_cost_plan(root: Path, protocol: Path, readiness: Path) -> CostPlan:
    """就绪目录必须包括本次固定脚本和两种完整模拟，缺一不申请预算。"""
    config, matrices = verify_protocol(root, protocol)
    require_full_t17(root, config, matrices)
    evidence = offline_evidence(root, readiness, model_digest(config))
    historical, samples = historical_usage(root, root / HISTORY)
    old = load_live_preregistration(root / "experiments/t17/preregistration.yaml")
    budgets = (
        old.model1_budget,
        old.model1_full_budget,
        old.model2_budget,
        old.model2_full_budget,
        old.defense_budget,
    )
    stages = tuple(
        stage_cost(root, matrix, budget, samples)
        for matrix, budget in zip(matrices, budgets, strict=True)
    )
    total = sum((s.budget.max_total_usd for s in stages), Decimal(0))
    return CostPlan(
        protocol_id=config.protocol_id,
        protocol_relative_path=protocol.resolve().relative_to(root.resolve()).as_posix(),
        configuration_sha256=model_digest(config),
        protocol_manifest=file_digest(protocol / "protocol-manifest.json"),
        created_at=datetime.now(UTC),
        historical=historical,
        offline_evidence=evidence,
        offline_relative_path=readiness.resolve().relative_to(root.resolve()).as_posix(),
        stages=stages,
        requested_max_total_usd=total,
        remaining_requested_usd=total,
    )


def write_cost_plan(root: Path, protocol: Path, readiness: Path, output: Path) -> CostPlan:
    """只创建新的提案文件；不更新旧报价，不隐式授权。"""
    output.resolve().relative_to(root.resolve())
    plan = build_cost_plan(root, protocol, readiness)
    write_checked_json(output, plan)
    return plan
