"""授权声明的无正文测量规格，由实际注册工具机械导出。"""

from typing import Annotated

from pydantic import Field

from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import CapabilityEffect


class ClaimActionSpec(StrictModel):
    """声明必须来自指定真实输入及其内容哈希，不能凭场景名判定。"""

    actor_id: NonEmptyStr
    action_id: NonEmptyStr
    input_index: Annotated[int, Field(ge=0)]
    expected_content_hash: Sha256
    requested_effect: CapabilityEffect
