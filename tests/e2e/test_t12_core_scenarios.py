import json
import shutil
from pathlib import Path

import yaml

from skillflow.benchmark.runner import ScenarioRunner
from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.models.enums import Decision, EnforcementMode
from skillflow.models.reports import RISK_REPORT_ADAPTER, RunRiskReport
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document

ROOT = Path("scenarios")


def _runner(decisions: dict[str, Decision] | None = None) -> ScenarioRunner:
    scripts, registered = t12_fixture_registry()
    return ScenarioRunner(scripts, registered if decisions is None else decisions)


def _report(path: Path) -> RunRiskReport:
    report = RISK_REPORT_ADAPTER.validate_python(json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(report, RunRiskReport)
    return report


def test_b0_and_g0_finish_the_task_without_unauthorized_effects(tmp_path: Path) -> None:
    cases = (
        ROOT / "benign" / "b0_legal_summary.yaml",
        ROOT / "benign" / "g0_legal_cross_skill.yaml",
    )

    reports = tuple(
        _report(_runner().run(path, tmp_path / path.stem, seed=f"t12-{path.stem}").risk_report_path)
        for path in cases
    )

    assert tuple(report.task_success for report in reports) == (True, True)
    assert tuple(report.uea.uea_count for report in reports) == (0, 0)


def test_b1_s1_and_l1_expose_one_target_uea_in_monitor_mode(tmp_path: Path) -> None:
    cases = (
        ROOT / "attacks" / "b1_direct_unauthorized.yaml",
        ROOT / "attacks" / "s1_scope_expansion.yaml",
        ROOT / "attacks" / "l1_session_lifetime_escape.yaml",
    )

    reports = tuple(
        _report(_runner().run(path, tmp_path / path.stem, seed=f"t12-{path.stem}").risk_report_path)
        for path in cases
    )

    assert tuple(report.uea.uea_count for report in reports) == (1, 1, 1)
    assert all(report.task_success is True for report in reports)


def test_all_deny_keeps_uea_zero_but_reports_task_failure(tmp_path: Path) -> None:
    source_path = ROOT / "benign" / "b0_legal_summary.yaml"
    scenario = validate_yaml_document(source_path, Scenario)
    restricted = scenario.model_copy(
        update={
            "execution": scenario.execution.model_copy(update={"mode": EnforcementMode.ENFORCE}),
            "oracle": scenario.oracle.model_copy(update={"expected_origins": ()}),
        }
    )
    scenario_path = tmp_path / "scenarios" / "benign" / "all-deny.yaml"
    scenario_path.parent.mkdir(parents=True)
    manifest_root = tmp_path / "scenarios" / "manifests"
    manifest_root.mkdir()
    shutil.copy2(ROOT / "manifests" / "summary-reader.yaml", manifest_root)
    scenario_path.write_text(
        yaml.safe_dump(restricted.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    denied = dict.fromkeys(t12_fixture_registry()[1], Decision.DENY)

    report = _report(
        _runner(denied).run(scenario_path, tmp_path / "all-deny", seed="t12-deny").risk_report_path
    )

    assert report.uea.uea_count == 0
    assert report.task_success is False


def test_enforce_blocks_b1_s1_and_l1_and_exposes_task_loss(tmp_path: Path) -> None:
    cases = (
        ROOT / "attacks" / "b1_direct_unauthorized.yaml",
        ROOT / "attacks" / "s1_scope_expansion.yaml",
        ROOT / "attacks" / "l1_session_lifetime_escape.yaml",
    )
    copied = tuple(
        _copy_with_mode(
            path,
            tmp_path,
            EnforcementMode.ENFORCE,
            retain_origin_expectations=False,
        )
        for path in cases
    )

    results = tuple(
        _runner().run(path, tmp_path / "runs" / path.stem, seed=f"t12-{path.stem}")
        for path in copied
    )
    reports = tuple(_report(result.risk_report_path) for result in results)

    assert all(result.receipts == () for result in results)
    assert tuple(report.uea.uea_count for report in reports) == (0, 0, 0)
    assert all(report.task_success is False for report in reports)


def test_enforce_keeps_b0_and_g0_successful_with_zero_uea(tmp_path: Path) -> None:
    cases = (
        ROOT / "benign" / "b0_legal_summary.yaml",
        ROOT / "benign" / "g0_legal_cross_skill.yaml",
    )
    copied = tuple(_copy_with_mode(path, tmp_path, EnforcementMode.ENFORCE) for path in cases)

    reports = tuple(
        _report(
            _runner()
            .run(path, tmp_path / "runs" / path.stem, seed=f"t12-{path.stem}")
            .risk_report_path
        )
        for path in copied
    )

    assert tuple(report.uea.uea_count for report in reports) == (0, 0)
    assert all(report.task_success is True for report in reports)


def _copy_with_mode(
    source: Path,
    root: Path,
    mode: EnforcementMode,
    *,
    retain_origin_expectations: bool = True,
) -> Path:
    scenario = validate_yaml_document(source, Scenario)
    variant = scenario.model_copy(
        update={
            "execution": scenario.execution.model_copy(update={"mode": mode}),
            "oracle": scenario.oracle.model_copy(
                update={
                    "expected_origins": (
                        scenario.oracle.expected_origins if retain_origin_expectations else ()
                    )
                }
            ),
        }
    )
    path = root / source
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest_root = root / "scenarios" / "manifests"
    if not manifest_root.exists():
        shutil.copytree(ROOT / "manifests", manifest_root)
    path.write_text(
        yaml.safe_dump(variant.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path
