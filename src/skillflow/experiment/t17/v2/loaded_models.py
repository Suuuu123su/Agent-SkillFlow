"""已验证的单阶段资料及原始文件清单。"""

from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.api_models import ApiUsageEvent
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix
from skillflow.experiment.t17.v2.frozen import FrozenFile
from skillflow.experiment.t17.v2.run_models import StageResult
from skillflow.models.base import NonEmptyStr, StrictModel


class LoadedStage(StrictModel):
    """阶段不得跨尝试拼接；真实用量与完整本地原始清单一同保留。"""

    configuration: V2Configuration
    matrix: V2Matrix
    result: StageResult
    raw_relative_path: NonEmptyStr
    raw_manifest: FrozenFile
    raw_files: dict[NonEmptyStr, FrozenFile]
    api_usage: tuple[ApiUsageEvent, ...] = ()

    def group(self) -> AnalysisGroup:
        """返回一个模型和执行域内的可复算测量组。"""
        return AnalysisGroup(
            self.configuration, self.result.cores, self.result.replays, (self.raw_manifest.sha256,)
        )
