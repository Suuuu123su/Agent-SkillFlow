from pathlib import Path

from skillflow.experiment.t16.budget import BudgetConfig
from skillflow.experiment.t16.matrix import (
    MatrixKind,
    load_matrix,
    validate_matrix_against_preregistration,
)
from skillflow.experiment.t16.preregistration import load_preregistration
from skillflow.experiment.t16.provider import PricingStatus, ProviderKind
from skillflow.validation import validate_yaml_document

T16_DIR = Path("experiments/t16")
PREREGISTRATION = T16_DIR / "preregistration.yaml"


def test_static_matrices_have_exact_counts_and_no_design_drift() -> None:
    # Given: T16-A 的预注册与三份静态矩阵。
    registration = load_preregistration(PREREGISTRATION)
    matrices = {
        MatrixKind.SMOKE: load_matrix(T16_DIR / "matrix_smoke.yaml"),
        MatrixKind.MODEL1: load_matrix(T16_DIR / "matrix_model1.yaml"),
        MatrixKind.MODEL2_SUBSET: load_matrix(T16_DIR / "matrix_model2_subset.yaml"),
    }

    # When: 对每份矩阵做机械重建比较。
    for matrix in matrices.values():
        validate_matrix_against_preregistration(matrix, registration)

    # Then: 链数固定，Smoke 覆盖全部 12 条件。
    assert len(matrices[MatrixKind.SMOKE].trials) == 48
    assert len(matrices[MatrixKind.MODEL1].trials) == 360
    assert len(matrices[MatrixKind.MODEL2_SUBSET].trials) == 72
    assert {item.condition_id for item in matrices[MatrixKind.SMOKE].trials} == {
        item.condition_id for item in registration.conditions
    }


def test_target_neutral_trials_share_pair_id_per_semantic_instance() -> None:
    # Given: 完整单模型矩阵与预注册配对组。
    registration = load_preregistration(PREREGISTRATION)
    matrix = load_matrix(T16_DIR / "matrix_model1.yaml")
    condition_groups = {item.condition_id: item.pair_group_id for item in registration.conditions}

    # When: 按能力匹配组、语义实例和重复号聚合。
    buckets: dict[tuple[str, str, int], set[str]] = {}
    for trial in matrix.trials:
        group = condition_groups[trial.condition_id]
        key = (group, trial.semantic_instance_id, trial.repeat_index)
        buckets.setdefault(key, set()).add(trial.pair_id)

    # Then: 同组 target/neutral/control 永远共享唯一 pair_id。
    assert all(len(pair_ids) == 1 for pair_ids in buckets.values())


def test_live_matrices_remain_pending_and_cost_config_defaults_closed() -> None:
    # Given: 三份矩阵和费用示例。
    smoke = load_matrix(T16_DIR / "matrix_smoke.yaml")
    model1 = load_matrix(T16_DIR / "matrix_model1.yaml")
    model2 = load_matrix(T16_DIR / "matrix_model2_subset.yaml")
    budget = validate_yaml_document(T16_DIR / "cost.example.yaml", BudgetConfig)

    # When / Then: Smoke 仅 Fake，Live 的价格仍待 T16-B 冻结，默认禁止执行。
    assert smoke.provider.kind is ProviderKind.FAKE
    assert model1.provider.kind is ProviderKind.LIVE
    assert model2.provider.kind is ProviderKind.LIVE
    assert model1.provider.pricing.status is PricingStatus.LIVE_PENDING
    assert model2.provider.pricing.status is PricingStatus.LIVE_PENDING
    assert budget.allow_live is False


def test_env_example_contains_only_safe_noncredential_controls() -> None:
    # Given: 仓库根目录的环境示例。
    content = Path(".env.example").read_text(encoding="utf-8")

    # When / Then: 只声明关闭开关和数值上限，不提供凭据槽位。
    assert "SKILLFLOW_T16_ALLOW_LIVE=false" in content
    forbidden = ("API_KEY", "SECRET", "PASSWORD", "BEARER")
    assert all(marker not in content.upper() for marker in forbidden)
