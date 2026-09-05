"""按既定分层导出原始响应延迟与模型失败分母，不推断未观测纯执行耗时。"""

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.v2.measurements import measure
from skillflow.experiment.t17.v2.statistics_models import Measurement
from skillflow.experiment.t19.accounting import LedgerInputs
from skillflow.experiment.t19.execution import CoreRecord
from skillflow.experiment.t19.reporting import PublicIndex, _strata


def operational_metrics(
    index: PublicIndex, records: dict[str, CoreRecord], ledger: LedgerInputs
) -> dict[str, Measurement]:
    """API计时读账本响应，模型失败率分母为实际模型决定。"""
    result = {}
    events = tuple(e for rows in ledger.journals.values() for e in rows)
    for label, trials in _strata(index.plan.trials).items():
        ids = tuple(t.trial_id for t in trials)
        cores = tuple(records[i] for i in ids if i in records)
        complete = len(cores) == len(trials)
        decisions = tuple(d for c in cores for d in c.decisions)
        for behavior in ("refusal", "no_call", "schema_rejection"):
            result[label + "/failure_rate/" + behavior] = measure(
                sum(d.behavior == behavior for d in decisions),
                len(decisions),
                ids,
                complete=complete,
                scope="actual_model_decisions_including_recovery",
            )
        responses = tuple(e for e in events if e.unit_id in ids and e.event_type == "response")
        result[label + "/latency.api_ms"] = measure(
            sum(e.latency_ms or 0 for e in responses),
            len(responses),
            tuple(e.event_sha256 for e in responses),
            complete=complete and all(e.latency_ms is not None for e in responses),
            scope="actual_core_API_responses_including_recovery",
            unit="milliseconds_per_response",
        )
        result[label + "/latency.exclusive_task_execution_ms"] = Measurement(
            status=MeasurementStatus.NOT_AVAILABLE,
            reason="仅采集整链、API与防御分段计时；未隔离纯任务执行，不能用相减伪造",
            unit="milliseconds",
            denominator_scope="exclusive_task_execution_without_harness_capture_evaluation",
            evidence_ids=ids,
        )
    return result
