import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from skillflow.experiment.matrix import MatrixExecutionRequest, execute_matrix
from skillflow.models.enums import Decision, ProvenanceMode
from skillflow.models.experiment_reports import ExperimentRiskReport
from skillflow.models.matrix import ExperimentMatrix
from skillflow.models.replay_reports import ReplayRiskReport
from skillflow.models.reports import RISK_REPORT_ADAPTER
from skillflow.models.run_reports import RunRiskReport
from skillflow.validation import validate_yaml_document

MATRIX_PATH = Path("scenarios/matrix/mvp.yaml")
RAW_FIXTURE_PAYLOADS = (
    "report-content-01",
    "context-canary01",
    '{"route":"out"}',
    '{"route":"log"}',
    "memory-target!",
    "memory-neutral",
    "claim-canary-001",
    "scope-allowed-01",
    "scope-adjacent1",
    "session-canary01",
)
EXPECTED_POSITIVE_REPLAYS = frozenset(
    {
        "replay-A1-a1-implicit-text-01-authorization-claim",
        "replay-C1-c1-context-grid-p11-01-context-input",
        "replay-C2-c2-tool-return-grid-p11-01-tool-return",
        "replay-G0-g0-drop-memory-01-memory-read",
        "replay-G0-g0-preserve-01-memory-read",
        "replay-M1-m1-drop-memory-01-memory-read",
        "replay-M1-m1-preserve-01-memory-read",
        "replay-M2-m2-target-revoked-01-m2-memory-1",
        "replay-M2-m2-target-revoked-02-m2-memory-3",
    }
)


class ExternalSideEffectBlockedError(RuntimeError):
    """T14 临时拦截器发现真实外部能力调用。"""


@dataclass(frozen=True, slots=True)
class MvpEvidence:
    root: Path
    runs: tuple[RunRiskReport, ...]
    replays: tuple[ReplayRiskReport, ...]
    experiment: ExperimentRiskReport


@pytest.fixture(scope="module")
def mvp_evidence(tmp_path_factory: pytest.TempPathFactory) -> MvpEvidence:
    """从 YAML 执行完整链路，同时让任何真实网络或进程调用立即失败。"""
    output = tmp_path_factory.mktemp("t14-mvp") / "matrix"
    matrix = validate_yaml_document(MATRIX_PATH, ExperimentMatrix)
    blocked = ExternalSideEffectBlockedError("MVP 只允许进程内 Mock Sink")
    with (
        patch("socket.socket", side_effect=blocked) as socket_constructor,
        patch("socket.create_connection", side_effect=blocked) as socket_connection,
        patch("subprocess.Popen", side_effect=blocked) as process_constructor,
        patch("subprocess.run", side_effect=blocked) as process_runner,
        patch("os.system", side_effect=blocked) as shell_runner,
    ):
        execute_matrix(
            MatrixExecutionRequest(
                matrix_path=MATRIX_PATH,
                matrix=matrix,
                output=output,
                determinism_repeats=1,
                redacted=True,
            )
        )
    assert not any(
        call.called
        for call in (
            socket_constructor,
            socket_connection,
            process_constructor,
            process_runner,
            shell_runner,
        )
    )
    runs = tuple(
        _run_report(output / "runs" / run_id / "run-report.json")
        for run_id in _manifest_ids(output, "run_ids")
    )
    replays = tuple(
        _replay_report(output / "replays" / replay_id / "replay-report.json")
        for replay_id in _manifest_ids(output, "replay_ids")
    )
    return MvpEvidence(
        root=output,
        runs=runs,
        replays=replays,
        experiment=_experiment_report(output / "experiment-report.json"),
    )


def test_authorized_path_completes_task_with_zero_uea(mvp_evidence: MvpEvidence) -> None:
    # Given/When: B0 已经通过 YAML→Trace→Graph→Metric→Report 完整链路
    report = _run_by_variant(mvp_evidence, "b0-monitor")

    # Then: 合法授权保留任务成功，且不制造未授权执行
    assert report.task_success is True
    assert report.uea.uea_count == 0
    assert report.effects
    assert all(effect.authorized and effect.receipt_id for effect in report.effects)


def test_context_composition_exposes_new_policy_denied_source_to_sink_path(
    mvp_evidence: MvpEvidence,
) -> None:
    # Given/When: 只打开 shared_context 的 p11 与关闭该桥梁的 p10
    closed = _run_by_variant(mvp_evidence, "c1-context-grid-p10")
    opened = _run_by_variant(mvp_evidence, "c1-context-grid-p11")

    # Then: 新路径落到 Policy 因来源拒绝的真实 Effect；Grant 真值仍保持为已授权
    assert closed.harm is False
    assert closed.source_to_sink_paths == ()
    assert opened.harm is True
    assert opened.uea.uea_count == 0
    assert opened.unauthorized_effects == ()
    effect = opened.effects[0]
    assert effect.authorized is True
    assert effect.policy_result is Decision.DENY
    assert "UNTRUSTED_ORIGIN" in effect.reason_codes
    assert any(
        f"effect:{effect.effect_id}" in path.node_ids for path in opened.source_to_sink_paths
    )


def test_revoked_memory_has_strict_rir_one_residual(mvp_evidence: MvpEvidence) -> None:
    # Given/When: M2 撤销后第一个 Session 的 Memory 被成对中和
    replay = _replay_by_id(
        mvp_evidence,
        "replay-M2-m2-target-revoked-01-m2-memory-1",
    )

    # Then: 只有带确认影响边的 Receipt Effect 才进入 RIR(1)
    assert replay.ci == 1
    assert replay.confirmed_influence_edges
    assert replay.original_receipt_ids
    assert mvp_evidence.experiment.rir_1.value is not None
    assert mvp_evidence.experiment.rir_1.value > 0


def test_implicit_text_authorization_disappears_after_claim_neutralization(
    mvp_evidence: MvpEvidence,
) -> None:
    # Given/When: A1 只删除低可信授权声明，其余输入保持一致
    replay = _replay_by_id(
        mvp_evidence,
        "replay-A1-a1-implicit-text-01-authorization-claim",
    )

    # Then: 原运行有 Receipt，中和后确认/拒绝且动作消失，ALR 为正
    assert replay.original_baseline_result is Decision.ALLOW
    assert replay.original_receipt_ids
    assert replay.neutralization_preserves_other_inputs
    assert replay.neutral_baseline_result in {Decision.CONFIRM, Decision.DENY}
    assert replay.y_original is True
    assert replay.y_neutral is False
    assert mvp_evidence.experiment.alr.value is not None
    assert mvp_evidence.experiment.alr.value > 0


def test_every_executed_sink_has_path_decision_and_receipt(
    mvp_evidence: MvpEvidence,
) -> None:
    for report in mvp_evidence.runs:
        for effect in report.effects:
            assert effect.executed
            assert effect.decision_id
            assert effect.receipt_id
            assert any(
                f"effect:{effect.effect_id}" in path.node_ids
                for path in report.source_to_sink_paths
            )


def test_scripted_oracle_and_causal_goldens_are_exact(mvp_evidence: MvpEvidence) -> None:
    for report in mvp_evidence.runs:
        precision = report.provenance.overall.precision
        recall = report.provenance.overall.recall
        if precision.value is not None:
            assert precision.value == 1.0
        if report.provenance_mode is ProvenanceMode.DROP_ON_MEMORY:
            assert recall.value is not None
            assert recall.value < 1.0
        elif recall.value is not None:
            assert recall.value == 1.0
    actual_positive = frozenset(replay.replay_id for replay in mvp_evidence.replays if replay.ci)
    assert actual_positive == EXPECTED_POSITIVE_REPLAYS
    assert all(replay.ci == 1 for replay in mvp_evidence.replays if replay.ci)


def test_risk_reports_do_not_leak_raw_payload_or_host_path(
    mvp_evidence: MvpEvidence,
) -> None:
    report_text = "\n".join(
        path.read_text(encoding="utf-8") for path in mvp_evidence.root.rglob("*report.json")
    )
    assert all(payload not in report_text for payload in RAW_FIXTURE_PAYLOADS)
    assert str(mvp_evidence.root) not in report_text
    assert '"blob_id"' not in report_text
    assert '"content"' not in report_text


def _manifest_ids(root: Path, field: str) -> tuple[str, ...]:
    value = json.loads((root / "experiment-manifest.json").read_text(encoding="utf-8"))[field]
    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)
    return tuple(value)


def _run_report(path: Path) -> RunRiskReport:
    report = RISK_REPORT_ADAPTER.validate_json(path.read_text(encoding="utf-8"))
    assert isinstance(report, RunRiskReport)
    return report


def _replay_report(path: Path) -> ReplayRiskReport:
    report = RISK_REPORT_ADAPTER.validate_json(path.read_text(encoding="utf-8"))
    assert isinstance(report, ReplayRiskReport)
    return report


def _experiment_report(path: Path) -> ExperimentRiskReport:
    report = RISK_REPORT_ADAPTER.validate_json(path.read_text(encoding="utf-8"))
    assert isinstance(report, ExperimentRiskReport)
    return report


def _run_by_variant(evidence: MvpEvidence, variant: str) -> RunRiskReport:
    return next(report for report in evidence.runs if report.variant == variant)


def _replay_by_id(evidence: MvpEvidence, replay_id: str) -> ReplayRiskReport:
    return next(report for report in evidence.replays if report.replay_id == replay_id)
