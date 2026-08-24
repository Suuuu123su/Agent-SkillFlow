"""所有外部输入模型共享的严格边界配置。"""

from typing import Annotated, TypeAlias

from pydantic import BaseModel, ConfigDict, StringConstraints

NonEmptyStr: TypeAlias = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StrictModel(BaseModel):
    """冻结且拒绝未知字段的 Pydantic 边界模型。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)
