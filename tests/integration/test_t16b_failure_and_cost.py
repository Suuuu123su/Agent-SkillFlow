from pathlib import Path

from skillflow.experiment.t16.dry_run import execute_fake_matrix
from skillflow.experiment.t16.dry_run_checks import (
    FailureInjectionKind,
    OperationalDisposition,
    build_cost_simulation_report,
    run_failure_injection_report,
)
from skillflow.experiment.t16.dry_run_records import load_t16b_config
from skillflow.experiment.t16.matrix import load_matrix
from skillflow.experiment.t16.preregistration import load_preregistration

T16_DIR = Path("experiments/t16")


def test_all_failure_injections_are_blocked_and_classified_separately(tmp_path: Path) -> None:
    # Given: 一条完整 Fake 结果集合与不允许 live 的费用配置。
    registration = load_preregistration(T16_DIR / "preregistration.yaml")
    matrix = load_matrix(T16_DIR / "matrix_model1.yaml")
    config = load_t16b_config(T16_DIR / "t16b_fake_dry_run.yaml")
    records = execute_fake_matrix(registration, matrix, config)

    # When: 执行 Provider、Schema、预算和网络失败注入。
    report = run_failure_injection_report(config, records)

    # Then: 必需失败均被阻断，invalid/refusal/no-call 保持不同操作分类。
    assert {item.kind for item in report.results} == set(FailureInjectionKind)
    assert report.all_blocked is True
    dispositions = {item.disposition for item in report.results}
    assert OperationalDisposition.REFUSAL in dispositions
    assert OperationalDisposition.NO_CALL in dispositions
    assert OperationalDisposition.INVALID_OTHER in dispositions
    assert report.classifications_are_distinct is True

    # When: 用模拟 Token 运行正常/最坏费用，并触发总费用安全停止。
    cost = build_cost_simulation_report(config, records[:3], tmp_path / "partial.jsonl")

    # Then: 三种链长各有正常/最坏结果，停止前结果仍留存。
    assert len(cost.cases) == 6
    assert cost.rates_are_hypothetical is True
    assert cost.fake_provider_billed_cost_usd == 0
    assert cost.partial_save.limit.value == "total_cost"
    assert cost.partial_save.saved_result_count == 2
    assert cost.partial_save.attempted_result_count == 3
    assert cost.partial_save.existing_results_saved is True
    assert (tmp_path / "partial.jsonl").read_text(encoding="utf-8").count("\n") == 2
