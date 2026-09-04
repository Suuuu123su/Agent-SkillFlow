"""离线验收必须检查事实、独立期望、执行域与零 API，不只信任通过标记。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from skillflow.experiment.t17.v2 import golden, readiness
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix
from skillflow.experiment.t17.v2.frozen import file_digest
from skillflow.experiment.t17.v2.golden_models import GoldenReport, golden_specification
from skillflow.experiment.t17.v2.loaded_models import LoadedStage
from skillflow.experiment.t17.v2.loading import load_stage, read_model
from skillflow.experiment.t17.v2.run_models import UnitUsage
from skillflow.experiment.t17.v2.runtime_models import DecisionFact
from skillflow.experiment.t17.v2.stage import StageSetup, run_stage


@pytest.fixture(scope="module")
def offline_stage(t17_cli_root: Path) -> LoadedStage:
    root = Path.cwd()
    protocol = root / "experiments/t17/v2"
    configuration = read_model(protocol / "preregistration.json", V2Configuration)
    matrix = read_model(protocol / "matrix-canary.json", V2Matrix)
    output = t17_cli_root / "scripted-reference"
    result = run_stage(StageSetup(root, output, configuration, matrix, "scripted", None))
    assert result.gate.passed
    return load_stage(root, output)


def expected_report(stage: LoadedStage) -> GoldenReport:
    spec = golden_specification()
    return GoldenReport(
        configuration_sha256=model_digest(stage.configuration),
        phase_contract_sha256=model_digest(stage.result.phase),
        expected_sha256=model_digest(spec),
        passed=True,
        core=24,
        replay=18,
        replicas=5,
        fingerprints=dict.fromkeys(spec.tasks, ("a" * 64,) * 5),
        tasks=spec.tasks,
        metrics=spec.expected_metrics,
    )


def patch_golden(stage: LoadedStage, monkeypatch: pytest.MonkeyPatch) -> Mock:
    monkeypatch.setattr(
        golden, "verify_protocol", Mock(return_value=(stage.configuration, (stage.matrix,)))
    )
    monkeypatch.setattr(golden, "run_stage", Mock(return_value=stage.result))
    cores = {core.identity.condition_id: core for core in stage.result.cores}
    execute = Mock(
        side_effect=lambda context, trial: SimpleNamespace(terminal=cores[trial.condition_id])
    )
    monkeypatch.setattr(golden, "execute_core", execute)
    return execute


def test_golden_checks_actual_reference_against_independent_expectations(
    offline_stage: LoadedStage,
    t17_cli_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replicas = patch_golden(offline_stage, monkeypatch)
    report = golden.run_golden(Path.cwd(), t17_cli_root, t17_cli_root / "golden-success")
    readiness.validate_golden(report, model_digest(offline_stage.configuration))
    assert replicas.call_count == 24 * 4
    assert report.actual_api_calls == 0
    assert report.raw_files.keys() == {"expected.json"}


def test_golden_keeps_all_independent_failure_reasons(
    offline_stage: LoadedStage,
    t17_cli_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_golden(offline_stage, monkeypatch)
    first, *rest = offline_stage.result.cores
    assert first.data is not None
    task = first.data.proof.task.model_copy(
        update={"task_success": False, "safe_task_success": False}
    )
    proof = first.data.proof.model_copy(update={"task": task})
    changed = first.model_copy(update={"data": first.data.model_copy(update={"proof": proof})})
    replays = tuple(
        replay.model_copy(update={"proof": None})
        if replay.identity.condition_id in {"c1-context-grid-p00", "c1-context-grid-p01"}
        else replay
        for replay in offline_stage.result.replays
    )
    result = offline_stage.result.model_copy(
        update={
            "cores": (changed, *rest),
            "replays": replays,
            "gate": offline_stage.result.gate.model_copy(update={"passed": False}),
        }
    )
    monkeypatch.setattr(golden, "run_stage", Mock(return_value=result))
    metrics = {name: SimpleNamespace(value=-1) for name in golden_specification().expected_metrics}
    monkeypatch.setattr(golden, "metric_vector", Mock(return_value=metrics))
    report = golden.run_golden(Path.cwd(), t17_cli_root, t17_cli_root / "golden-failed")
    assert not report.passed
    assert set(report.failures) == {
        "full_phase_gate",
        "independent_task_expectations",
        "independent_risk_expectations",
        "five_replica_determinism",
        "neutral_control_causal_zero",
    }


@pytest.mark.parametrize("missing", ["matrix", "core"])
def test_golden_rejects_missing_registered_input(
    offline_stage: LoadedStage,
    missing: str,
    t17_cli_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_golden(offline_stage, monkeypatch)
    if missing == "matrix":
        matrix = offline_stage.matrix.model_copy(
            update={"trials": offline_stage.matrix.trials[:-1]}
        )
        monkeypatch.setattr(
            golden, "verify_protocol", Mock(return_value=(offline_stage.configuration, (matrix,)))
        )
        reason = "requires_exact_registered_matrix"
    else:
        core = offline_stage.result.cores[0].model_copy(update={"data": None})
        result = offline_stage.result.model_copy(
            update={"cores": (core, *offline_stage.result.cores[1:])}
        )
        monkeypatch.setattr(golden, "run_stage", Mock(return_value=result))
        reason = "golden_core_missing"
    with pytest.raises(ValueError, match=reason):
        golden.run_golden(Path.cwd(), t17_cli_root, t17_cli_root / f"golden-missing-{missing}")


@pytest.mark.parametrize(
    "field",
    [
        "passed",
        "failures",
        "configuration_sha256",
        "expected_sha256",
        "core",
        "replay",
        "replicas",
        "tasks",
        "metrics",
        "fingerprint_keys",
        "fingerprint_count",
        "fingerprint_drift",
    ],
)
def test_golden_summary_rejects_independent_readiness_drift(
    offline_stage: LoadedStage,
    field: str,
) -> None:
    report = expected_report(offline_stage)
    updates = {
        "passed": False,
        "failures": ("synthetic_failure",),
        "configuration_sha256": "b" * 64,
        "expected_sha256": "b" * 64,
        "core": 23,
        "replay": 17,
        "replicas": 4,
        "tasks": {},
        "metrics": {},
    }
    if field.startswith("fingerprint_"):
        fingerprints = dict(report.fingerprints)
        name = next(iter(fingerprints))
        if field == "fingerprint_keys":
            fingerprints.pop(name)
        else:
            fingerprints[name] = ("a" * 64,) * 4
            if field == "fingerprint_drift":
                fingerprints[name] += ("b" * 64,)
        update = {"fingerprints": fingerprints}
    else:
        update = {field: updates[field]}
    changed = GoldenReport.model_validate(report.model_copy(update=update).model_dump())
    with pytest.raises(ValueError, match="offline_golden_not_ready"):
        readiness.validate_golden(changed, model_digest(offline_stage.configuration))


def write_readiness(directory: Path, report: GoldenReport) -> None:
    for name in ("golden/reference", "fake-all", "fake-none"):
        path = directory / name
        path.mkdir(parents=True)
        (path / "raw-manifest.json").write_text("{}", encoding="utf-8")
    manifest = directory / "golden/reference/raw-manifest.json"
    report = report.model_copy(
        update={"raw_files": {"reference/raw-manifest.json": file_digest(manifest).sha256}}
    )
    (directory / "golden/golden-report.json").write_text(report.model_dump_json(), encoding="utf-8")


def fake_stage(stage: LoadedStage, *, all_actions: bool) -> LoadedStage:
    decision = DecisionFact(
        run_id="local-test-run",
        session_id="local-test-session",
        step_id="local-test-step",
        call_id="local-test-call",
        implementation="readiness-test-stub",
        allowed_action_ids=("local-safe-action",),
        selected_action_ids=("local-safe-action",) if all_actions else (),
        behavior="normal" if all_actions else "no_call",
        schema_valid=True,
    )
    cores = tuple(core.model_copy(update={"decisions": (decision,)}) for core in stage.result.cores)
    replays = tuple(
        replay.model_copy(update={"decisions": (decision,)}) for replay in stage.result.replays
    )
    result = stage.result.model_copy(
        update={
            "phase": stage.result.phase.model_copy(update={"domain": "fake_reference"}),
            "cores": cores,
            "replays": replays,
        }
    )
    return stage.model_copy(update={"result": result})


def drift_stage(reference: LoadedStage, drift: str) -> LoadedStage:
    result = reference.result
    if drift == "gate":
        result = result.model_copy(
            update={"gate": result.gate.model_copy(update={"passed": False})}
        )
    elif drift == "configuration":
        reference = reference.model_copy(
            update={
                "configuration": reference.configuration.model_copy(
                    update={"protocol_id": "changed"}
                )
            }
        )
    elif drift == "domain":
        result = result.model_copy(
            update={"phase": result.phase.model_copy(update={"domain": "live_reference"})}
        )
    elif drift == "core_count":
        result = result.model_copy(update={"cores": result.cores[:-1]})
    elif drift == "replay_count":
        result = result.model_copy(update={"replays": result.replays[:-1]})
    elif drift == "unit_api":
        core = result.cores[0].model_copy(update={"usage": UnitUsage(api_calls=1)})
        result = result.model_copy(update={"cores": (core, *result.cores[1:])})
    return reference.model_copy(update={"result": result})


@pytest.mark.parametrize(
    "drift",
    [
        "none",
        "file_set",
        "raw_hash",
        "phase_binding",
        "gate",
        "configuration",
        "domain",
        "core_count",
        "replay_count",
        "unit_api",
        "choice_all",
        "choice_none",
        "choice_schema",
    ],
)
def test_offline_evidence_checks_files_binding_domain_zero_api_and_choices(
    offline_stage: LoadedStage,
    drift: str,
    t17_cli_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = t17_cli_root / f"readiness-{drift}"
    report = expected_report(offline_stage)
    if drift == "phase_binding":
        report = report.model_copy(update={"phase_contract_sha256": "b" * 64})
    write_readiness(directory, report)
    if drift in {"file_set", "raw_hash"}:
        path = (
            directory
            / "golden"
            / ("extra.txt" if drift == "file_set" else "reference/raw-manifest.json")
        )
        path.write_text("changed", encoding="utf-8")
    reference = drift_stage(offline_stage, drift)
    all_actions = fake_stage(offline_stage, all_actions=drift != "choice_all")
    no_actions = fake_stage(offline_stage, all_actions=drift == "choice_none")
    if drift == "choice_schema":
        core = all_actions.result.cores[0]
        core = core.model_copy(
            update={"decisions": (core.decisions[0].model_copy(update={"schema_valid": False}),)}
        )
        all_actions = all_actions.model_copy(
            update={
                "result": all_actions.result.model_copy(
                    update={"cores": (core, *all_actions.result.cores[1:])}
                )
            }
        )
    monkeypatch.setattr(
        readiness, "load_stage", Mock(side_effect=[reference, all_actions, no_actions])
    )
    errors = {
        "file_set": "golden_file_set_drift",
        "raw_hash": "golden_raw_hash_drift",
        "phase_binding": "golden_phase_binding",
        "unit_api": "offline_evidence_is_not_zero_api",
        "choice_all": "fake_choice_drift",
        "choice_none": "fake_choice_drift",
        "choice_schema": "fake_choice_drift",
    }
    if drift != "none":
        with pytest.raises(ValueError, match=errors.get(drift, "offline_stage_not_ready")):
            readiness.offline_evidence(
                Path.cwd(), directory, model_digest(offline_stage.configuration)
            )
    else:
        evidence = readiness.offline_evidence(
            Path.cwd(), directory, model_digest(offline_stage.configuration)
        )
        assert len(evidence) == 4
        assert all(not Path(name).is_absolute() for name in evidence)
