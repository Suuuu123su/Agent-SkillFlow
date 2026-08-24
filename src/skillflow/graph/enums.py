"""T07 图节点、边与边界的封闭枚举。"""

from enum import StrEnum, unique


@unique
class GraphNodeKind(StrEnum):
    """SecurityGraph 固定支持的节点类型。"""

    ARTIFACT = "artifact"
    EVENT = "event"
    PRINCIPAL = "principal"
    GRANT = "grant"
    DECISION = "decision"
    EFFECT = "effect"


@unique
class ProvenanceRelation(StrEnum):
    """Artifact-Event 二部图的两类核心边。"""

    USED = "USED"
    GENERATED = "GENERATED"


@unique
class SecurityRelation(StrEnum):
    """任务书固定的安全语义边。"""

    READ = "READ"
    WRITE = "WRITE"
    LOAD = "LOAD"
    INVOKE = "INVOKE"
    DERIVE = "DERIVE"
    PERSIST = "PERSIST"
    AUTHORIZE = "AUTHORIZE"
    INFLUENCE_CANDIDATE = "INFLUENCE_CANDIDATE"
    INFLUENCE_CONFIRMED = "INFLUENCE_CONFIRMED"
    REVOKE = "REVOKE"


@unique
class BoundaryKind(StrEnum):
    """路径深度需要分别累计的五类边界。"""

    CONTEXT = "context"
    MEMORY = "memory"
    SESSION = "session"
    SKILL = "skill"
    TOOL = "tool"
