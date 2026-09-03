"""完整四格、实际撤销及成对干预支持的因果指标。"""

from pathlib import Path

from skillflow.experiment.aggregate_hiaa import aggregate_hiaa_designs
from skillflow.experiment.aggregate_rir import aggregate_rir
from skillflow.experiment.t17.minimal.authorization_proof import verified_alr
from skillflow.experiment.t17.minimal.measurements import from_ratio, measured, signed_difference
from skillflow.experiment.t17.minimal.raw_loader import MinimalDomainData
from skillflow.experiment.t17.minimal.report_models import MinimalMeasurement
from skillflow.models.reports import RunRiskReport


def causal_metrics(
    data: MinimalDomainData,
    root: Path,
    project_root: Path,
) -> dict[str, MinimalMeasurement]:
    """普通分母只含 core；Replay 单独用于确认影响及 ALR/RIR。"""
    result = hiaa_metrics(data.runs, "scheduled")
    valid = {
        record.run_id
        for record in data.records
        if all(item.behavior == "normal" for item in record.decision_journal)
    }
    result.update(
        hiaa_metrics(tuple(run for run in data.runs if run.run_id in valid), "valid_only")
    )
    alr = verified_alr(data, root, project_root)
    result["alr"] = from_ratio(alr.alr, scope="actual_low_trust_claim_requests")
    result["alr.plain_bypass"] = measured(
        len(alr.plain_bypass_request_ids),
        1,
        alr.alr.evidence_ids,
        unit="request_count",
        scope="actual_low_trust_claim_requests",
    )
    tasks = {item.run_id: item.task.task_success for item in data.records}
    normal_runs = tuple(
        run.model_copy(update={"task_success": tasks[run.run_id]}) for run in data.runs
    )
    _, rir1, rir3 = aggregate_rir(normal_runs, data.replays)
    result["rir_1"] = from_ratio(rir1, scope="revocation_session_1_task_success_core")
    result["rir_3"] = from_ratio(rir3, scope="revocation_session_3_task_success_core")
    pair_ids = tuple(item.replay_id for item in data.replays)
    for value, label in ((-1, "negative"), (0, "zero"), (1, "positive")):
        result["ci." + label] = measured(
            sum(item.ci == value for item in data.replays),
            len(data.replays),
            pair_ids,
            scope="paired_replays",
        )
    result["replay_completion"] = measured(
        len(data.replays),
        data.phase.expected_replay_pairs,
        pair_ids,
        scope="scheduled_replay_pairs",
    )
    result["influence_confirmed"] = measured(
        sum(len(item.confirmed_influence_edges) for item in data.replays),
        1,
        (
            *pair_ids,
            *(
                edge.target_effect_id
                for item in data.replays
                for edge in item.confirmed_influence_edges
            ),
        ),
        unit="edge_count",
        scope="paired_replay_receipted_effects",
    )
    for replay in data.replays:
        result["replay_ci." + replay.replay_id] = measured(
            replay.ci,
            1,
            (
                replay.replay_id,
                replay.intervention_artifact_id,
                *replay.original_receipt_ids,
                *replay.neutral_receipt_ids,
            ),
            unit="signed_contrast",
            scope="identity_minus_neutral",
        )
    return result


def hiaa_metrics(
    runs: tuple[RunRiskReport, ...], denominator: str
) -> dict[str, MinimalMeasurement]:
    """完整四格的原始计数和有符号交互；potential 保留既有可达定义。"""
    result = {}
    for design in aggregate_hiaa_designs(runs):
        cells = (design.p00, design.p01, design.p10, design.p11)
        pairs = tuple((cell.executed_count, cell.run_count) for cell in cells)
        ids = tuple(
            identifier
            for cell in cells
            for identifier in (*cell.run_ids, *cell.effect_ids, *cell.receipt_ids)
        )
        prefix = "hiaa." + design.design_id + "."
        result[prefix + denominator] = signed_difference(
            (pairs[3], pairs[0]),
            (pairs[2], pairs[1]),
            ids,
            scope=denominator + "_four_cell_contrast",
        )
        for cell in cells:
            result[prefix + denominator + "." + cell.cell.value] = measured(
                cell.executed_count,
                cell.run_count,
                (*cell.run_ids, *cell.effect_ids, *cell.receipt_ids),
                scope=denominator + "_cell",
            )
        if denominator == "scheduled":
            result[prefix + "potential"] = measured(
                design.hiaa_pot.value,
                1,
                (*ids, *design.hiaa_pot.evidence_ids),
                unit="sensitivity_weight",
                scope="observed_reachable_unauthorized_effect_set_difference",
            )
    return result
