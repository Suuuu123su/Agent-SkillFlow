"""交付明细的类型边界，区分建议防御、实际选择和真实效果。"""

from typing import Annotated, Literal

from pydantic import Field

from skillflow.defense.models import (
    AttackDiagnosis,
    AttackSignalVector,
    DefenseId,
    DefenseOutcome,
    DefensePlan,
)
from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.experiment.t18.dataset import FileDigest
from skillflow.experiment.t18.matrix import Domain
from skillflow.models.base import NonEmptyStr, StrictModel


class DiagnosisRow(StrictModel):
    """绑定实际请求的信号与诊断，不把标签作为运行时输入。"""

    domain: Domain
    trial_id: NonEmptyStr
    run_id: NonEmptyStr
    request_event_id: NonEmptyStr
    signals: AttackSignalVector
    diagnosis: AttackDiagnosis


class PlanRow(StrictModel):
    """建议与实际选择分别保存，授权真值沿用原始决策。"""

    domain: Domain
    trial_id: NonEmptyStr
    run_id: NonEmptyStr
    request_event_id: NonEmptyStr
    proposed_plan: DefensePlan
    actual_defense_ids: tuple[DefenseId, ...]
    authorized: bool
    executed: bool
    actual_extra_steps: Annotated[int, Field(ge=0)]


class OutcomeRow(StrictModel):
    """一次既定配对的输出行，不代表额外实验或独立样本。"""

    domain: Domain
    comparison_id: NonEmptyStr
    before_trial_id: NonEmptyStr
    after_trial_id: NonEmptyStr
    outcome: DefenseOutcome


class TableFile(FileDigest):
    """一个交付文件的字节数、摘要和数据行数（不含表头）。"""

    records: Annotated[int, Field(ge=0)]


class TableManifest(StrictModel):
    """登记派生明细的来源域，禁止跨域汇总指标。"""

    schema_version: Literal["18.0"] = "18.0"
    domains: tuple[Domain, ...]
    source_phase_contracts: dict[Domain, Sha256]
    files: dict[NonEmptyStr, TableFile]
