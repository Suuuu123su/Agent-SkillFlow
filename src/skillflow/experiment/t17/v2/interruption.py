"""子进程硬退出的旁路证据；不覆盖它已经产生的任何原始文件。"""

from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.campaign import budget_proposal, partial_usage
from skillflow.experiment.t17.v2.campaign_models import StageOutcome
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.frozen import file_digest
from skillflow.experiment.t17.v2.interruption_records import interrupted_terminals
from skillflow.experiment.t17.v2.session_models import InterruptionManifest
from skillflow.experiment.t17.v2.unit_execution import compact_id, file_inventory
from skillflow.experiment.t17.v2.worker_models import StageJob


def interrupted_outcome(job: StageJob, reason: str) -> StageOutcome:
    """读取已结束子进程的目录，所有未终态化单元另存为中断或未运行。"""
    prepared, phase = job.prepared, job.approved_phase
    root, matrix = prepared.setup.root, prepared.matrices[job.index]
    directory = prepared.setup.output / matrix.stage.value / f"attempt-{job.attempt_number:02d}"
    raw, recovery = directory / "raw", directory / "recovery"
    recovery.mkdir(parents=True, exist_ok=False)
    write_checked_json(recovery / "phase-contract.json", phase)
    write_checked_json(recovery / "matrix.json", matrix)
    records, preserved = interrupted_terminals(phase, matrix, raw, reason)
    for record in records:
        write_checked_json(recovery / (compact_id(record.identity.unit_id) + ".json"), record)
    write_checked_json(
        recovery / "interruption-manifest.json",
        InterruptionManifest(
            phase_contract_sha256=model_digest(phase),
            reason=reason,
            scheduled_core=phase.scheduled_core,
            scheduled_replay=phase.scheduled_replay,
            preserved_terminals=preserved,
            interrupted_terminals=tuple(record.identity.unit_id for record in records),
            files=file_inventory(directory, directory),
        ),
    )
    maximum = budget_proposal(
        prepared, job.index, job.previous, failed=job.failed, attempt_number=job.attempt_number
    ).attempt_budget.max_total_usd
    outcome = StageOutcome(
        stage=matrix.stage,
        attempt_number=job.attempt_number,
        status="failed",
        reason=reason,
        raw_relative_path=raw.resolve().relative_to(root.resolve()).as_posix(),
        raw_manifest=file_digest(raw / "raw-manifest.json")
        if (raw / "raw-manifest.json").is_file()
        else None,
        interruption_manifest=file_digest(recovery / "interruption-manifest.json"),
        usage=partial_usage(raw, maximum),
    )
    write_checked_json(directory / "supervisor-stage-result.json", outcome)
    return outcome
