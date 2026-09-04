"""阶段完整性按冻结调度判断，模型失败不能伪装成基础设施失败。"""

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.api_models import ApiUsageEvent
from skillflow.experiment.t17.v2.config_models import V2Matrix
from skillflow.experiment.t17.v2.gate_checks import (
    binding_coverage,
    metric_statuses,
    usage_complete,
)
from skillflow.experiment.t17.v2.run_models import (
    CoreTerminal,
    PhaseContract,
    PhaseGate,
    ReplayTerminal,
    StageResult,
)


def build_gate(
    phase: PhaseContract,
    matrix: V2Matrix,
    group: AnalysisGroup,
    api_usage: tuple[ApiUsageEvent, ...] = (),
    *,
    source_phases: tuple[PhaseContract, ...] = (),
) -> PhaseGate:
    """统计数量、实际绑定、全部指标和逐调用用量缺一不可。"""
    configuration, cores, replays = group.configuration, group.cores, group.replays
    gate = _coverage_gate(phase, cores, replays)
    result = StageResult(
        phase=phase, cores=cores, replays=replays, gate=gate, source_phases=source_phases
    )
    binding = binding_coverage(configuration, matrix, result)
    statuses = metric_statuses(configuration, result)
    usage = usage_complete(matrix, result, api_usage)
    failures = list(gate.failures)
    if binding != 1.0:
        failures.append("trusted_binding_coverage")
    if not statuses or any(
        s not in {MeasurementStatus.MEASURED, MeasurementStatus.NOT_APPLICABLE}
        for s in statuses.values()
    ):
        failures.append("required_metric_statuses")
    if not usage:
        failures.append("response_usage_binding")
    return gate.model_copy(
        update={
            "passed": not failures,
            "binding_coverage": binding,
            "metric_statuses": statuses,
            "usage_complete": usage,
            "failures": tuple(failures),
        }
    )


def _coverage_gate(
    phase: PhaseContract, cores: tuple[CoreTerminal, ...], replays: tuple[ReplayTerminal, ...]
) -> PhaseGate:
    """每条调度必须终态化，且每条可评估任务都应具备完整可信证据。"""
    records: tuple[CoreTerminal | ReplayTerminal, ...] = (*cores, *replays)
    complete = sum(c.status == "completed" for c in cores)
    replay_done = sum(r.status == "completed" for r in replays)
    replay_na = sum(r.status == "not_applicable" for r in replays)
    infra = sum(r.status == "infrastructure_invalid" for r in records)
    protocol = sum(r.status == "protocol_error" for r in records)
    binding = sum(r.status == "evidence_binding_failure" for r in records)
    required = tuple(
        h for c in cores if c.data is not None for h in c.data.proof.hooks if h.required
    )
    hook_coverage = (
        sum(h.status is MeasurementStatus.MEASURED for h in required) / len(required)
        if required
        else 0.0
    )
    tasks = sum(c.data is not None for c in cores) / phase.scheduled_core
    facts = tuple(c.data.facts for c in cores if c.data is not None) + tuple(
        branch
        for r in replays
        if r.proof is not None
        for branch in (r.proof.original, r.proof.neutral)
    )
    effects = sum(sum(e.executed for e in f.effects) for f in facts)
    receipts = sum(len(f.receipts) for f in facts)
    receipt_coverage = min(receipts / effects, 1.0) if effects else 1.0
    failures = []
    if (
        len(cores) != phase.scheduled_core
        or len(replays) != phase.scheduled_replay
        or len({r.identity.unit_id for r in records}) != len(records)
    ):
        failures.append("scheduled_terminal_coverage")
    if complete != phase.scheduled_core or replay_done + replay_na != phase.scheduled_replay:
        failures.append("scheduled_evidence_coverage")
    if infra or protocol or binding:
        failures.append("invalid_units")
    if tasks != 1.0 or receipt_coverage != 1.0 or hook_coverage != 1.0:
        failures.append("required_evidence_coverage")
    return PhaseGate(
        passed=False,
        scheduled_core=phase.scheduled_core,
        scheduled_replay=phase.scheduled_replay,
        terminal_core=len(cores),
        terminal_replay=len(replays),
        completed_core=complete,
        evaluated_replay=replay_done,
        not_applicable_replay=replay_na,
        infrastructure_invalid=infra,
        protocol_errors=protocol,
        binding_failures=binding,
        task_evidence_coverage=tasks,
        receipt_coverage=receipt_coverage,
        required_hook_coverage=hook_coverage,
        failures=tuple(failures),
    )
