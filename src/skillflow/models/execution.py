"""T13 Experiment 与 Run 的持久化清单。"""

from enum import StrEnum, unique
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.matrix_axes import MatrixRunRole
from skillflow.models.references import ScenarioPath

SafeIdentifier = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$", max_length=120),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


@unique
class ExecutionBackend(StrEnum):
    """T13 允许的离线执行后端。"""

    SCRIPTED = "scripted"


@unique
class ExperimentKind(StrEnum):
    """Experiment 的公开入口类型。"""

    SINGLE_RUN = "single_run"
    FACTORIAL = "factorial"
    MATRIX = "matrix"


class ArtifactDigest(StrictModel):
    """一个不含宿主路径的派生产物摘要。"""

    name: NonEmptyStr
    sha256: Sha256


class RunManifest(StrictModel):
    """重建 Run 派生产物所需的稳定输入清单。"""

    schema_version: Literal["0.1"] = "0.1"
    run_id: SafeIdentifier
    experiment_id: SafeIdentifier
    scenario: ScenarioPath
    scenario_id: NonEmptyStr
    variant: SafeIdentifier
    seed: int
    backend: ExecutionBackend
    run_role: MatrixRunRole
    redacted: bool
    task_success: bool
    harm: bool
    artifacts: tuple[ArtifactDigest, ...]


class DeterminismCheck(StrictModel):
    """一个核心 Run 的重复次数与规范产物摘要。"""

    run_id: SafeIdentifier
    repeats: Annotated[int, Field(ge=1)]
    consistent: bool
    fingerprint: Sha256


class ExperimentManifest(StrictModel):
    """Experiment 的入口、成员和确定性检查清单。"""

    schema_version: Literal["0.1"] = "0.1"
    experiment_id: SafeIdentifier
    kind: ExperimentKind
    source: NonEmptyStr
    backend: ExecutionBackend
    redacted: bool
    determinism_repeats: Annotated[int, Field(ge=1)]
    run_ids: tuple[SafeIdentifier, ...]
    replay_ids: tuple[SafeIdentifier, ...] = ()
    determinism_checks: tuple[DeterminismCheck, ...] = ()
