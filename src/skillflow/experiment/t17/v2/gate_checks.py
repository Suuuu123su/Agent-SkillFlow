"""阶段门逐项验证实际证据，不以文件存在或样本数量代替验证。"""

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.api_models import ApiUsageEvent
from skillflow.experiment.t17.v2.binding import validate_core_binding, validate_replay_binding
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix
from skillflow.experiment.t17.v2.journal import verify_journal
from skillflow.experiment.t17.v2.metrics import metric_vector
from skillflow.experiment.t17.v2.phase_sources import phase_index
from skillflow.experiment.t17.v2.run_models import CoreTerminal, ReplayTerminal, StageResult
from skillflow.experiment.t17.v2.stage_contract import unit_identity
from skillflow.experiment.t17.v2.usage_validation import validate_usage


def binding_coverage(config: V2Configuration, matrix: V2Matrix, result: StageResult) -> float:
    """每个预定单元的身份、保存点、会话、来源、权限和回执都需要复核。"""
    cores = {c.identity.trial_id: c for c in result.cores}
    trials = {t.trial_id: t for t in matrix.trials}
    records: tuple[CoreTerminal | ReplayTerminal, ...] = (*result.cores, *result.replays)
    verified = 0
    phases = phase_index(result)
    for record in records:
        trial = trials.get(record.identity.trial_id)
        if trial is None or record.status not in {"completed", "not_applicable"}:
            continue
        phase = phases.get(record.identity.phase_contract_sha256)
        if phase is None or record.identity != unit_identity(
            phase, matrix, trial, record.identity.unit_id
        ):
            continue
        if isinstance(record, ReplayTerminal) and (
            trial.replay_pair_ids.get(record.target_alias) != record.identity.unit_id
        ):
            continue
        try:
            if isinstance(record, CoreTerminal):
                validate_core_binding(config, record)
            else:
                validate_replay_binding(cores[record.identity.trial_id], record)
        except (KeyError, ValueError):
            continue
        verified += 1
    scheduled = result.phase.scheduled_core + result.phase.scheduled_replay
    return min(verified / scheduled, 1.0) if scheduled else 0.0


def metric_statuses(config: V2Configuration, result: StageResult) -> dict[str, MeasurementStatus]:
    """真正执行完整投影；实现错误导致验收失败，不填零来通过。"""
    try:
        values = metric_vector(AnalysisGroup(config, result.cores, result.replays))
        return {name: value.status for name, value in values.items()}
    except Exception:  # noqa: BLE001 -- 留存全部终态，阶段门失败，禁止进入下一付费阶段。
        return {}


def usage_complete(
    matrix: V2Matrix, result: StageResult, events: tuple[ApiUsageEvent, ...]
) -> bool:
    """逐响应日志必须可重算并与每条真实执行决策一一绑定。"""
    try:
        verify_journal(events, allowed_phases=frozenset(phase_index(result)))
        validate_usage(result, matrix, events)
    except ValueError:
        return False
    return True
