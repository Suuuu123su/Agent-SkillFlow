"""T16-D.2 Model1 与 T16-E Model2 Canary 的冻结包装层。"""

from skillflow.experiment.t16.live_agent_calls import LiveAgentClient
from skillflow.experiment.t16.t16e_analysis import (
    T16EComparisonInputs,
    build_t16e_comparison,
)
from skillflow.experiment.t16.t16e_integrity import load_t16e_model1_baseline
from skillflow.experiment.t16.task_success_canary_engine import execute_canary_run
from skillflow.experiment.t16.task_success_canary_engine_support import (
    CANARY_COUNT,
    OUTPUT_ROOT_NOT_EMPTY,
    CanaryRunContract,
    T16D2CanaryRunError,
    T16D2CanaryRunRequest,
)
from skillflow.experiment.t16.task_success_canary_models import T16D2CanaryRunSummary
from skillflow.experiment.t16.task_success_live_config import (
    T16D2R_PROTOCOL_ID,
    build_t16d2r_canary_config,
    build_t16e_canary_config,
)
from skillflow.experiment.t16.task_success_live_run_support import T16D2ProgressSink
from skillflow.experiment.t16.task_success_live_store import (
    load_t16d2_raw_records,
    write_immutable_json,
)


def execute_t16d2r_canary_run(
    request: T16D2CanaryRunRequest,
    client: LiveAgentClient,
    progress: T16D2ProgressSink | None = None,
) -> T16D2CanaryRunSummary:
    """执行独立的 GPT-5.6 Luna 11 条 Canary。"""
    contract = CanaryRunContract(
        build_t16d2r_canary_config(request.project_root),
        T16D2R_PROTOCOL_ID,
    )
    return execute_canary_run(request, contract, client, progress)


def execute_t16e_canary_run(
    request: T16D2CanaryRunRequest,
    client: LiveAgentClient,
    progress: T16D2ProgressSink | None = None,
) -> T16D2CanaryRunSummary:
    """执行独立的 GPT-5.5 固定快照 11 条 Canary。"""
    model1 = load_t16e_model1_baseline(request.project_root)
    contract = CanaryRunContract(
        build_t16e_canary_config(request.project_root),
        T16D2R_PROTOCOL_ID,
    )
    summary = execute_canary_run(request, contract, client, progress)
    if summary.status == "PASSED":
        model2_records = load_t16d2_raw_records(request.output_root / "raw-trials.jsonl")
        comparison = build_t16e_comparison(
            T16EComparisonInputs(
                model1.summary,
                model1.records,
                summary,
                model2_records,
            )
        )
        write_immutable_json(request.output_root / "cross-model-comparison.json", comparison)
    return summary


__all__ = (
    "CANARY_COUNT",
    "OUTPUT_ROOT_NOT_EMPTY",
    "T16D2CanaryRunError",
    "T16D2CanaryRunRequest",
    "execute_t16d2r_canary_run",
    "execute_t16e_canary_run",
)
