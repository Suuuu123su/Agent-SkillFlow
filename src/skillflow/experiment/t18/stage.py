"""短批次正式执行；跳过已绑定终态，不覆盖旧目录或隐含重采样。"""

import hashlib
import json
from pathlib import Path

import typer

from skillflow.experiment.t17.v2.configuration import canonical_digest
from skillflow.experiment.t18.catalog_models import LocalCatalog
from skillflow.experiment.t18.controls import bind_matrix_controls
from skillflow.experiment.t18.execution import CoreContext, execute_core
from skillflow.experiment.t18.matrix import Domain, LocalMatrix
from skillflow.experiment.t18.preregistration import Preregistration
from skillflow.experiment.t18.replay import LocalReplay, ReplayBudget
from skillflow.experiment.t18.rule_freeze import verify_rules
from skillflow.experiment.t18.run_models import LocalCore, LocalPhase
from skillflow.validation import validate_yaml_document

MAX_BATCH_CORES = 48
HARNESS_DIRECTORIES = (
    "adapters",
    "benchmark",
    "instrumentation",
    "policy",
    "runtime",
    "store",
)


def load_inputs(root: Path, domain: Domain) -> tuple[Preregistration, LocalMatrix, LocalCatalog]:
    """从静态输入读取，不现场重新生成内容或选择新样本。"""
    config = validate_yaml_document(root / "experiments/t18/preregistration.yaml", Preregistration)
    catalog = validate_yaml_document(root / "experiments/t18/skill-catalog.yaml", LocalCatalog)
    matrix = config.scripted if domain == "scripted" else config.fake_reference
    name = "matrix-scripted.yaml" if domain == "scripted" else "matrix-fake-smoke.yaml"
    if validate_yaml_document(root / "experiments/t18" / name, LocalMatrix) != matrix:
        raise ValueError("t18_static_matrix_drift")
    if canonical_digest(catalog.model_dump(mode="json")) != config.catalog_sha256:
        raise ValueError("t18_catalog_contract_drift")
    if bind_matrix_controls(matrix, catalog) != config.hiaa_controls[domain]:
        raise ValueError("t18_hiaa_control_drift")
    verify_rules(root)
    return config, matrix, catalog


def _phase(
    root: Path, output: Path, domain: Domain
) -> tuple[LocalPhase, LocalMatrix, LocalCatalog]:
    config, matrix, catalog = load_inputs(root, domain)
    path = output / "phase-contract.json"
    if path.exists():
        phase = LocalPhase.model_validate_json(path.read_text(encoding="utf-8"))
        for relative, expected in phase.runtime_sources.items():
            if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
                raise ValueError("t18_phase_runtime_drift:" + relative)
    else:
        sources = tuple(sorted((root / "src/skillflow/defense").glob("*.py"))) + tuple(
            sorted((root / "src/skillflow/experiment/t18").glob("*.py"))
        )
        sources += tuple(
            sorted(
                {
                    p
                    for name in HARNESS_DIRECTORIES
                    for p in (root / "src/skillflow" / name).rglob("*.py")
                }
            )
        )
        phase = LocalPhase(
            domain=domain,
            matrix_sha256=canonical_digest(matrix.model_dump(mode="json")),
            catalog_sha256=config.catalog_sha256,
            preregistration_sha256=canonical_digest(config.model_dump(mode="json")),
            runtime_sources={
                p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sources
            },
            scheduled_core=len(matrix.cores),
            max_replay_pairs=matrix.max_replay_pairs,
        )
        output.mkdir(parents=True, exist_ok=False)
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(phase.model_dump_json(indent=2) + "\n")
    if (
        phase.domain != domain
        or phase.catalog_sha256 != config.catalog_sha256
        or phase.matrix_sha256 != canonical_digest(matrix.model_dump(mode="json"))
        or phase.preregistration_sha256 != canonical_digest(config.model_dump(mode="json"))
    ):
        raise ValueError("t18_phase_configuration_drift")
    return phase, matrix, catalog


def run_batch(
    root: Path, output: Path, domain: Domain, maximum_cores: int = 24
) -> dict[str, int | str]:
    """最多运行一个短批次，仍有未完成任务时调用方继续下一批即可。"""
    root, output = root.resolve(), output.resolve()
    if not output.is_relative_to(root) or output == root or not output.name.startswith("t18-"):
        raise ValueError("t18_new_project_directory_required")
    if not 1 <= maximum_cores <= MAX_BATCH_CORES:
        raise ValueError("t18_short_batch_required")
    phase, matrix, catalog = _phase(root, output, domain)
    phase_hash = canonical_digest(phase.model_dump(mode="json"))
    by_id = {s.skill_variant_id: s for s in catalog.skills}
    replays = tuple(
        LocalReplay.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted((output / "replay").glob("p*/portable-replay.json"))
    )
    budget = ReplayBudget(matrix.max_replay_pairs, len(replays))
    if len(tuple((output / "replay").glob("p*"))) != budget.used:
        raise ValueError("t18_partial_replay_requires_recovery")
    context = CoreContext(root, output, domain, phase_hash, budget)
    completed = 0
    added = 0
    for number, cell in enumerate(matrix.cores, 1):
        terminal = output / "terminals" / f"c{number:03d}.json"
        if terminal.exists():
            record = LocalCore.model_validate_json(terminal.read_text(encoding="utf-8"))
            if (
                record.phase_contract_sha256 != phase_hash
                or record.cell != cell
                or record.domain != domain
            ):
                raise ValueError("t18_core_contract_drift")
            if record.status != "completed":
                raise ValueError("t18_failed_terminal_not_resampled")
            completed += 1
            continue
        if added >= maximum_cores:
            continue
        execute_core(context, by_id[cell.skill_variant_id], cell, number)
        completed += 1
        added += 1
        typer.echo(
            json.dumps(
                {
                    "domain": domain,
                    "completed": completed,
                    "scheduled": len(matrix.cores),
                    "replay_pairs": budget.used,
                    "api_calls": 0,
                },
                ensure_ascii=False,
            ),
        )
    return {
        "domain": domain,
        "completed": completed,
        "scheduled": len(matrix.cores),
        "new_core": added,
        "replay_pairs": budget.used,
        "api_calls": 0,
    }
