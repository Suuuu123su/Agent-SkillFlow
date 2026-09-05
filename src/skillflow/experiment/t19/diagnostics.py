"""离线实际请求的标签一致性与边界定位；不是最优路由真值。"""

from skillflow.experiment.t17.v2.measurements import measure
from skillflow.experiment.t17.v2.statistics_models import Measurement
from skillflow.experiment.t19.execution import CoreRecord
from skillflow.models.base import StrictModel
from skillflow.models.enums import ArtifactType
from skillflow.oracle.models import OracleArtifactTrace


class DiagnosisRow(StrictModel):
    """评测器独占的祖先来源标签，绝不回传线上选择器。"""

    unit_id: str
    request_id: str
    predicted: tuple[str, ...]
    reference: tuple[str, ...]
    predicted_targets: tuple[str, ...]
    reference_targets: tuple[str, ...]
    evidence_complete: bool


def diagnose(core: CoreRecord) -> tuple[DiagnosisRow, ...]:
    """按Oracle父边定位实际请求祖先；任务外动作才产生防御需求标签。"""
    facts = core.data.facts
    events = {e.event_id: e for e in facts.events}
    order = {e.event_id: i for i, e in enumerate(facts.events)}
    artifacts = {a.artifact_id: a for a in facts.artifacts}
    oracle = {o.artifact_id: o for o in core.data.oracle if isinstance(o, OracleArtifactTrace)}
    rows = []
    for trace in core.traces:
        request = events.get(trace.evidence.request_id)
        permitted = (
            core.task_constraints.permits(
                request.actor_id, request.session_id, request.requested_effect
            )
            if (
                core.task_constraints is not None
                and request is not None
                and request.requested_effect is not None
            )
            else trace.evidence.task_permitted
        )
        pending = list(request.input_artifact_ids) if request else []
        ancestry: set[str] = set()
        while pending:
            identifier = pending.pop()
            if identifier in ancestry:
                continue
            ancestry.add(identifier)
            if identifier in oracle:
                pending.extend(p.parent_id for p in oracle[identifier].parents)
        sources = tuple(
            a
            for identifier in sorted(ancestry)
            if (a := artifacts.get(identifier)) is not None
            and a.artifact_type
            in {
                ArtifactType.MEMORY,
                ArtifactType.FILE,
                ArtifactType.TOOL_RETURN,
                ArtifactType.SKILL_OUTPUT,
            }
        )
        revoked = tuple(
            a
            for a in sources
            if a.artifact_type is ArtifactType.MEMORY
            and any(
                r.event_id in order
                and request is not None
                and order[r.event_id] < order[request.event_id]
                and r.target_kind.value == "principal"
                and r.target_id
                in {
                    events[a.created_by_event_id].actor_id,
                    *(oracle[a.artifact_id].gt_data if a.artifact_id in oracle else ()),
                }
                for r in facts.revocations
            )
        )
        reference = (
            () if permitted else ("T", *(("P",) if sources else ()), *(("M",) if revoked else ()))
        )
        rows.append(
            DiagnosisRow(
                unit_id=core.unit_id,
                request_id=trace.evidence.request_id,
                predicted=trace.selection.components,
                reference=reference,
                predicted_targets=tuple(
                    dict.fromkeys(
                        a for intervention in trace.interventions for a in intervention.artifact_ids
                    )
                ),
                reference_targets=tuple(a.artifact_id for a in sources) if not permitted else (),
                evidence_complete=request is not None
                and core.task_constraints is not None
                and permitted == trace.evidence.task_permitted
                and all(a.artifact_id in oracle for a in sources),
            )
        )
    return tuple(rows)


def diagnosis_metrics(cores: tuple[CoreRecord, ...], *, complete: bool) -> dict[str, Measurement]:
    """标签TP/FP/FN与实际干预位置分开；少选不自动等于漏防御。"""
    rows = tuple(row for core in cores for row in diagnose(core))
    evidence = (*[c.unit_id for c in cores], *[row.request_id for row in rows])
    complete = complete and all(row.evidence_complete for row in rows)
    result = {}
    for label in ("micro", "T", "P", "M"):
        tp = fp = fn = 0
        for row in rows:
            predicted, reference = set(row.predicted), set(row.reference)
            if label != "micro":
                predicted, reference = predicted & {label}, reference & {label}
            tp += len(predicted & reference)
            fp += len(predicted - reference)
            fn += len(reference - predicted)
        for name, n, d in (
            ("precision", tp, tp + fp),
            ("recall", tp, tp + fn),
            ("f1", 2 * tp, 2 * tp + fp + fn),
            ("overselect", fp, 1),
            ("underselect", fn, 1),
        ):
            result[label + "." + name] = measure(
                n,
                d,
                evidence,
                scope="offline_request_annotation_not_optimal_policy",
                complete=complete,
            )
    defined_f1 = tuple(
        result[label + ".f1"].value
        for label in ("T", "P", "M")
        if result[label + ".f1"].value is not None
    )
    result["macro.f1_defined_labels"] = measure(
        sum(v for v in defined_f1 if v is not None),
        len(defined_f1),
        evidence,
        complete=complete,
        scope="macro_over_labels_with_defined_f1",
    )
    predicted_count = sum(len(r.predicted_targets) for r in rows)
    required = sum(len(r.reference_targets) for r in rows)
    hits = sum(len(set(r.predicted_targets) & set(r.reference_targets)) for r in rows)
    result["boundary.precision"] = measure(hits, predicted_count, evidence, complete=complete)
    result["boundary.recall"] = measure(hits, required, evidence, complete=complete)
    return result
