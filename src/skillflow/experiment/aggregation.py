"""只从标准 RunResult/ReplayResult 机械聚合 ExperimentReport。"""

from dataclasses import dataclass

from skillflow.analysis.authorization_laundering import calculate_alr
from skillflow.experiment.aggregate_alr import authorization_attempts
from skillflow.experiment.aggregate_hiaa import aggregate_hiaa_designs, empty_hiaa
from skillflow.experiment.aggregate_rir import aggregate_rir
from skillflow.models.matrix_axes import MatrixRunRole
from skillflow.models.reports import (
    ExperimentRiskReport,
    RawCounts,
    ReplayRiskReport,
    RunRiskReport,
)
from skillflow.models.scenario_parts import EffectSelector


@dataclass(frozen=True, slots=True)
class StandardAggregationInput:
    """一次聚合允许读取的标准报告集合。"""

    experiment_id: str
    runs: tuple[RunRiskReport, ...]
    replays: tuple[ReplayRiskReport, ...]
    fallback_selector: EffectSelector


def aggregate_standard_results(source: StandardAggregationInput) -> ExperimentRiskReport:
    """不读取 Runtime、Blob 或场景正文，生成可复算聚合报告。"""
    core_runs = tuple(run for run in source.runs if run.run_role is MatrixRunRole.CORE)
    designs = aggregate_hiaa_designs(core_runs)
    primary = designs[0] if designs else empty_hiaa(source.fallback_selector)
    attempts = calculate_alr(authorization_attempts(core_runs, source.replays))
    revocation, rir_1, rir_3 = aggregate_rir(core_runs, source.replays)
    return ExperimentRiskReport(
        schema_version="0.1",
        report_scope="experiment",
        experiment_id=source.experiment_id,
        run_ids=tuple(run.run_id for run in core_runs),
        replay_ids=tuple(replay.replay_id for replay in source.replays),
        raw_counts=RawCounts(
            run_count=len(core_runs),
            replay_count=len(source.replays),
            unauthorized_executed_count=sum(run.uea.uea_count for run in core_runs),
            implicit_authorization_liability_count=attempts.alr.numerator,
        ),
        harm_selector=primary.harm_selector,
        p00=primary.p00,
        p01=primary.p01,
        p10=primary.p10,
        p11=primary.p11,
        HIAA_pot=primary.hiaa_pot,
        HIAA_run=primary.hiaa_run,
        hiaa_designs=designs,
        ALR=attempts.alr,
        authorization_attempts=attempts.attempts,
        authorization_laundering_request_ids=attempts.laundering_request_ids,
        plain_authorization_bypass_request_ids=attempts.plain_bypass_request_ids,
        revocation=revocation,
        RIR_1=rir_1,
        RIR_3=rir_3,
    )
