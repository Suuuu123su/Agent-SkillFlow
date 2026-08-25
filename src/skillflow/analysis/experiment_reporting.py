"""把 T11 中立事实聚合为 Experiment 风险报告。"""

from dataclasses import dataclass

from skillflow.analysis.authorization_laundering import (
    AuthorizationAttemptFact,
    calculate_alr,
)
from skillflow.analysis.errors import AnalysisInvariantError
from skillflow.analysis.hiaa import (
    MatrixRunOutcome,
    ReachableUnauthorizedEffect,
    calculate_hiaa,
    calculate_hiaa_potential,
)
from skillflow.analysis.metric_helpers import ratio_metric
from skillflow.analysis.residual_influence import calculate_rir
from skillflow.models.reports import ExperimentRiskReport, RawCounts
from skillflow.models.residual_metrics import (
    ResidualRunObservation,
    SkillRevocationRecord,
)
from skillflow.models.scenario_parts import EffectSelector


@dataclass(frozen=True, slots=True)
class ExperimentAggregationFacts:
    """生成 ExperimentReport 所需的跨 Run/Replay 中立事实。"""

    experiment_id: str
    run_ids: tuple[str, ...]
    replay_ids: tuple[str, ...]
    unauthorized_executed_count: int
    harm_selector: EffectSelector
    matrix_outcomes: tuple[MatrixRunOutcome, ...]
    harness_off_effects: tuple[ReachableUnauthorizedEffect, ...]
    harness_on_effects: tuple[ReachableUnauthorizedEffect, ...]
    authorization_attempts: tuple[AuthorizationAttemptFact, ...]
    revocation: SkillRevocationRecord | None
    residual_runs: tuple[ResidualRunObservation, ...]


def build_experiment_report(facts: ExperimentAggregationFacts) -> ExperimentRiskReport:
    """只读取结构化聚合事实，不耦合 Runtime 或场景 ID。"""
    if facts.unauthorized_executed_count < 0:
        raise AnalysisInvariantError(
            "build_experiment_report",
            "unauthorized_executed_count 不能为负",
        )
    declared_runs = set(facts.run_ids)
    observed_runs = {
        *(outcome.run_id for outcome in facts.matrix_outcomes),
        *(run.run_id for run in facts.residual_runs),
    }
    if not observed_runs.issubset(declared_runs):
        raise AnalysisInvariantError(
            "build_experiment_report",
            "四格或撤销后观察包含未声明的 run_id",
        )
    hiaa = calculate_hiaa(facts.harm_selector, facts.matrix_outcomes)
    potential = calculate_hiaa_potential(
        facts.harness_off_effects,
        facts.harness_on_effects,
    )
    laundering = calculate_alr(facts.authorization_attempts)
    if facts.revocation is None:
        rir_1 = ratio_metric(0, 0, ())
        rir_3 = ratio_metric(0, 0, ())
    else:
        rir_1 = calculate_rir(facts.revocation, facts.residual_runs, 1)
        rir_3 = calculate_rir(facts.revocation, facts.residual_runs, 3)
    return ExperimentRiskReport(
        schema_version="0.1",
        report_scope="experiment",
        experiment_id=facts.experiment_id,
        run_ids=facts.run_ids,
        replay_ids=facts.replay_ids,
        raw_counts=RawCounts(
            run_count=len(facts.run_ids),
            replay_count=len(facts.replay_ids),
            unauthorized_executed_count=facts.unauthorized_executed_count,
            implicit_authorization_liability_count=laundering.alr.numerator,
        ),
        harm_selector=hiaa.harm_selector,
        p00=hiaa.p00,
        p01=hiaa.p01,
        p10=hiaa.p10,
        p11=hiaa.p11,
        HIAA_pot=potential,
        HIAA_run=hiaa.hiaa_run,
        ALR=laundering.alr,
        authorization_attempts=laundering.attempts,
        authorization_laundering_request_ids=laundering.laundering_request_ids,
        plain_authorization_bypass_request_ids=laundering.plain_bypass_request_ids,
        revocation=facts.revocation,
        RIR_1=rir_1,
        RIR_3=rir_3,
    )
