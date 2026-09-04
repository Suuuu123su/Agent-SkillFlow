from pathlib import Path

from skillflow.experiment.t18.catalog import build_catalog
from skillflow.experiment.t18.execution import CoreContext, execute_core
from skillflow.experiment.t18.hiaa import HiaaTrial, compute_hiaa
from skillflow.experiment.t18.matrix import build_matrix
from skillflow.experiment.t18.replay import ReplayBudget

ROOT = Path(__file__).resolve().parents[3]


def test_fake_hiaa_complete_quartets_use_real_evidence(tmp_path: Path) -> None:
    matrix = build_matrix("fake_reference")
    catalog = {s.skill_variant_id: s for s in build_catalog(ROOT, include_held_out=False).skills}
    selected = {trial for g in matrix.hiaa_groups for trial in g.cells.values()}
    budget = ReplayBudget(8)
    samples = []
    for number, cell in enumerate(matrix.cores, 1):
        if cell.trial_id not in selected:
            continue
        record = execute_core(
            CoreContext(ROOT, tmp_path, matrix.domain, "0" * 64, budget),
            catalog[cell.skill_variant_id],
            cell,
            number,
        )
        assert record.data is not None
        samples.append(
            HiaaTrial(
                domain=matrix.domain,
                trial_id=cell.trial_id,
                run_id=record.run_id,
                complete=True,
                valid=all(d.behavior == "normal" for d in record.decisions),
                target_effect=bool(record.data.proof.task.risk_effect_ids),
                evidence_ids=record.data.proof.task.evidence_ids,
                refusal=False,
                no_call=False,
                schema_failure=False,
                task_failure=not record.data.proof.task.task_success,
            )
        )
    reports = compute_hiaa(matrix, tuple(samples))
    assert all(r.status == "measured" for r in reports)
    assert all(
        c.scheduled.denominator == c.valid_only.denominator == 1
        for r in reports
        for c in r.cells.values()
    )
    assert all(r.scheduled.value == r.valid_only.value for r in reports)
    assert budget.used == 2
