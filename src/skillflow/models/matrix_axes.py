"""T12 MVP Matrix 的封闭控制轴。"""

from enum import StrEnum, unique


@unique
class SkillStateCondition(StrEnum):
    """目标 Skill 在核心配置中的状态。"""

    NORMAL = "normal"
    REVOKED = "revoked"


@unique
class SessionCondition(StrEnum):
    """Effect 位于授权原 Session 或新 Session。"""

    ORIGINAL = "original"
    NEW = "new"


@unique
class AuthorizationCondition(StrEnum):
    """实验中被暴露的授权来源条件。"""

    NONE = "none"
    IMPLICIT_TEXT = "implicit_text"
    STRUCTURED_CONFIRMATION = "structured_confirmation"


@unique
class MatrixRunRole(StrEnum):
    """核心变体与不得进入普通分母的派生 Run。"""

    CORE = "core"
    DETERMINISM_REPEAT = "determinism_repeat"
    COUNTERFACTUAL = "counterfactual"
