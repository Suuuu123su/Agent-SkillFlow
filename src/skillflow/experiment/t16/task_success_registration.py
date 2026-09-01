"""v3 Task Success 配置加载、绑定与静态 Matrix 漂移检查。"""

from pathlib import Path

from skillflow.experiment.t16.task_success_matrix import (
    TaskSuccessMatrixDriftError,
    TaskSuccessSmokeMatrix,
    build_task_success_smoke_matrix,
)
from skillflow.experiment.t16.task_success_prereg_models import (
    TaskSuccessPreregistrationV3,
)
from skillflow.experiment.t16.task_success_spec_models import (
    TaskSuccessSpecificationRegistry,
)
from skillflow.validation import validate_yaml_document


def load_task_success_registry(path: Path) -> TaskSuccessSpecificationRegistry:
    """读取严格的 v3 Task Success specification。"""
    return validate_yaml_document(path, TaskSuccessSpecificationRegistry)


def load_task_success_preregistration(path: Path) -> TaskSuccessPreregistrationV3:
    """读取严格的 v3 bridge/calibration 预注册。"""
    return validate_yaml_document(path, TaskSuccessPreregistrationV3)


def load_task_success_smoke_matrix(path: Path) -> TaskSuccessSmokeMatrix:
    """读取默认禁止 live 的 48 链 Smoke Matrix。"""
    return validate_yaml_document(path, TaskSuccessSmokeMatrix)


def validate_task_success_matrix(
    matrix: TaskSuccessSmokeMatrix,
    registration: TaskSuccessPreregistrationV3,
    registry: TaskSuccessSpecificationRegistry,
) -> None:
    """验证三份静态文件相互绑定且与机械展开完全一致。"""
    if registration.task_success_specification_id != registry.id:
        raise TaskSuccessMatrixDriftError(matrix.id, registration.id)
    if registration.evaluator_id != registry.evaluator_id:
        raise TaskSuccessMatrixDriftError(matrix.id, registration.id)
    if registration.evaluator_version != registry.evaluator_version:
        raise TaskSuccessMatrixDriftError(matrix.id, registration.id)
    specs = {item.spec_id: item for item in registry.conditions}
    for condition in registration.conditions:
        spec = specs.get(condition.task_success_spec_id)
        if spec is None or spec.condition_id != condition.condition_id:
            raise TaskSuccessMatrixDriftError(matrix.id, registration.id)
        if spec.task_output_contract_id != condition.task_output_contract_id:
            raise TaskSuccessMatrixDriftError(matrix.id, registration.id)
    _validate_pair_fingerprints(registration, registry)
    if matrix != build_task_success_smoke_matrix(registration):
        raise TaskSuccessMatrixDriftError(matrix.id, registration.id)


def _validate_pair_fingerprints(
    registration: TaskSuccessPreregistrationV3,
    registry: TaskSuccessSpecificationRegistry,
) -> None:
    by_spec = {item.spec_id: item for item in registry.conditions}
    groups: dict[str, list[str]] = {}
    for condition in registration.conditions:
        groups.setdefault(condition.pair_group_id, []).append(condition.task_success_spec_id)
    for spec_ids in groups.values():
        if len(spec_ids) == 1:
            continue
        fingerprints = {by_spec[item].contract_fingerprint for item in spec_ids}
        if len(fingerprints) != 1:
            raise TaskSuccessMatrixDriftError(
                "task-success-specifications-v3",
                registration.id,
            )
