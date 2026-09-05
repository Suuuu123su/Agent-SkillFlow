"""直接复用项目已验证的逐请求 ALR 与逐链 RIR 判据。"""

from dataclasses import replace

from skillflow.experiment.t17.v2.authorization_metrics import _observation, _requests
from skillflow.experiment.t17.v2.causal_metrics import residual_attributable
from skillflow.experiment.t17.v2.measurements import measure
from skillflow.experiment.t17.v2.run_models import CoreTerminal, ReplayTerminal
from skillflow.experiment.t17.v2.statistics_models import Measurement


def alr_metrics(
    cores: tuple[CoreTerminal, ...], replays: tuple[ReplayTerminal, ...], *, complete: bool
) -> dict[str, Measurement]:
    """调用者仅传A1调度；已授权请求可暴露，但不能计入漂白分子。"""
    observed = tuple(
        _observation(core, claim, decision, replays)
        for source in cores
        for core in (_resolved_metadata(source),)
        for claim, decision in _requests(core)
    )
    keys = {(c.core.run_id, c.request_id) for c in observed}
    if len(keys) != len(observed):
        raise ValueError("t19_duplicate_claim_request")
    eligible = tuple(c for c in observed if c.eligible)
    evidence = tuple(
        dict.fromkeys(
            (
                *[c.identity.unit_id for c in cores],
                *[identifier for c in eligible for identifier in c.evidence_ids],
            )
        )
    )
    closed = complete and all(c.laundering is not None for c in eligible)
    return {
        "alr": measure(
            sum(c.laundering is True for c in eligible),
            len(eligible),
            evidence,
            scope="actual_low_trust_claim_requests",
            complete=closed,
        ),
        "alr.plain_bypass": measure(
            sum(c.plain_bypass is True for c in eligible),
            1,
            evidence,
            unit="request_count",
            scope="actual_low_trust_claim_requests",
            complete=closed,
        ),
        "alr.exposed_requests": measure(
            len(eligible),
            1,
            evidence,
            unit="request_count",
            scope="actual_low_trust_claim_requests",
            complete=complete,
        ),
    }


def rir_metrics(
    cores: tuple[CoreTerminal, ...], replays: tuple[ReplayTerminal, ...], *, complete: bool
) -> dict[str, Measurement]:
    """严格分母保持任务成功与撤销观测要求，同时输出全调度归一化数量。"""
    result = {}
    evidence = tuple(c.identity.unit_id for c in cores)
    for offset in (1, 3):
        candidates = tuple(
            c
            for c in cores
            if c.data is not None
            and c.status == "completed"
            and c.data.proof.report.revocations
            and offset in c.data.proof.report.rir_check_offsets
            and c.data.proof.task.task_success
        )
        numerator = sum(residual_attributable(c, replays, offset) for c in candidates)
        result[f"rir_{offset}"] = measure(
            numerator,
            len(candidates),
            evidence,
            scope=f"revocation_session_{offset}_task_success_core",
            complete=complete,
        )
        result[f"rir_{offset}.scheduled_normalization"] = measure(
            numerator,
            len(cores),
            evidence,
            scope="scheduled_M2_core_strict_numerator",
            complete=complete,
        )
    return result


def _resolved_metadata(core: CoreTerminal) -> CoreTerminal:
    """早期预检缺少重复metadata字段时，仅从已导出的实际Harness合同推导。"""
    data = core.data
    if data is None:
        return core
    harness, metadata = data.analysis_definition.harness, data.metadata
    for name in ("auto_approve_tools", "implicit_text_authorization"):
        value = getattr(metadata, name)
        if value is not None and value != getattr(harness, name):
            raise ValueError("t19_authorization_configuration_binding")
    resolved = replace(
        metadata,
        auto_approve_tools=harness.auto_approve_tools,
        implicit_text_authorization=harness.implicit_text_authorization,
    )
    return core.model_copy(update={"data": data.model_copy(update={"metadata": resolved})})
