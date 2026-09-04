"""标准数据集清单、源阶段和完整报告集合。"""

from typing import Annotated, Literal

from pydantic import Field

from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix
from skillflow.experiment.t17.v2.frozen import FrozenFile
from skillflow.experiment.t17.v2.report_models import ComparisonReport, MetricVectorReport
from skillflow.experiment.t17.v2.run_models import PhaseContract, PhaseGate
from skillflow.models.base import NonEmptyStr, StrictModel


class DatasetFile(StrictModel):
    """字节哈希与逻辑记录数分开，CSV 引号换行不改变记录计数。"""

    content: FrozenFile
    schema_path: NonEmptyStr
    record_count: Annotated[int, Field(ge=0)]
    format: Literal["json", "jsonl", "csv", "text"]


class DatasetStage(StrictModel):
    """完整冻结输入与本地原始文件清单，不复制私有请求或响应正文。"""

    configuration: V2Configuration
    matrix: V2Matrix
    phase: PhaseContract
    source_phases: tuple[PhaseContract, ...] = ()
    gate: PhaseGate
    raw_relative_path: NonEmptyStr
    raw_manifest: FrozenFile
    raw_files: dict[NonEmptyStr, FrozenFile]


class DatasetReports(StrictModel):
    """无论导出还是复算，都从同一结构化事实生成各层完整报告。"""

    schema_version: Literal["2.0"] = "2.0"
    vectors: tuple[MetricVectorReport, ...]
    comparisons: tuple[ComparisonReport, ...]


class ReportIndex(StrictModel):
    """完整报告分卷索引，文件名不是结果或排序判定依据。"""

    schema_version: Literal["2.0"] = "2.0"
    vectors: tuple[NonEmptyStr, ...]
    comparisons: tuple[NonEmptyStr, ...]


class DatasetManifest(StrictModel):
    """只描述实际提供的阶段，不把离线验证或单次预检标为完整 T17。"""

    schema_version: Literal["2.0"] = "2.0"
    dataset_id: NonEmptyStr
    protocol_id: NonEmptyStr
    scope: Literal["provided_stages_not_project_completion"] = (
        "provided_stages_not_project_completion"
    )
    stages: tuple[DatasetStage, ...]
    files: dict[NonEmptyStr, DatasetFile]
    tables: dict[NonEmptyStr, tuple[NonEmptyStr, ...]]
    scheduled_core: Annotated[int, Field(ge=0)]
    scheduled_replay: Annotated[int, Field(ge=0)]
    all_provided_stages_passed: bool
    contains_live_data: bool
    full_project_completion_claim: Literal[False] = False
