"""SkillFlow 的封闭枚举。"""

from enum import StrEnum, unique
from typing import assert_never


@unique
class PrincipalType(StrEnum):
    """能够产生事件或签发授权的主体类别。"""

    USER = "user"
    TRUSTED_POLICY = "trusted_policy"
    HARNESS = "harness"
    SKILL = "skill"
    TOOL = "tool"


@unique
class ArtifactType(StrEnum):
    """不可变数据版本的类别。"""

    CONTEXT = "context"
    MEMORY = "memory"
    FILE = "file"
    SKILL_OUTPUT = "skill_output"
    TOOL_ARG = "tool_arg"
    TOOL_RETURN = "tool_return"


@unique
class EventType(StrEnum):
    """追加式安全事件类别。"""

    RUN_START = "run_start"
    RUN_END = "run_end"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SKILL_INSTALL = "skill_install"
    SKILL_LOAD = "skill_load"
    SKILL_INVOKE = "skill_invoke"
    SKILL_RETURN = "skill_return"
    SKILL_REVOKE = "skill_revoke"
    SKILL_UNLOAD = "skill_unload"
    CONTEXT_ADD = "context_add"
    CONTEXT_READ = "context_read"
    CONTEXT_SUMMARIZE = "context_summarize"
    MEMORY_WRITE = "memory_write"
    MEMORY_READ = "memory_read"
    MEMORY_DELETE = "memory_delete"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    TOOL_CALL_REQUEST = "tool_call_request"
    TOOL_CALL_ALLOW = "tool_call_allow"
    TOOL_CALL_DENY = "tool_call_deny"
    TOOL_CALL_RESULT = "tool_call_result"
    AUTH_CLAIM_OBSERVED = "auth_claim_observed"
    AUTH_GRANT = "auth_grant"
    AUTH_REVOKE = "auth_revoke"
    ARTIFACT_REGISTER = "artifact_register"
    ARTIFACT_DERIVE = "artifact_derive"
    SENSITIVE_EFFECT = "sensitive_effect"


@unique
class Lifetime(StrEnum):
    """授权或效果的有效边界。"""

    CALL = "call"
    TASK = "task"
    SESSION = "session"
    PERSISTENT = "persistent"


@unique
class Scope(StrEnum):
    """MVP 中互不放大的四种精确作用域。"""

    EXACT_FILE = "exact-file"
    EXACT_KEY = "exact-key"
    EXACT_SINK = "exact-sink"
    COMMAND = "command"


@unique
class TrustLevel(StrEnum):
    """数据来源的保守信任等级。"""

    TRUSTED = "trusted"
    USER = "user"
    UNTRUSTED = "untrusted"
    UNKNOWN = "unknown"


@unique
class ProvenanceMode(StrEnum):
    """Harness 对 Observed 来源标签的受控处理模式。"""

    PRESERVE = "preserve"
    DROP_ON_DERIVE = "drop_on_derive"
    DROP_ON_MEMORY = "drop_on_memory"


@unique
class Decision(StrEnum):
    """Harness 或策略的结构化决策。"""

    ALLOW = "allow"
    DENY = "deny"
    CONFIRM = "confirm"


@unique
class CapabilityAction(StrEnum):
    """MVP 固定支持的能力动作。"""

    FILE_READ = "file.read"
    FILE_WRITE = "file.write"
    MEMORY_READ = "memory.read"
    MEMORY_WRITE = "memory.write"
    NETWORK_SEND = "network.send"
    SHELL_EXECUTE = "shell.execute"
    USER_CONFIRM = "user.confirm"


@unique
class EnforcementMode(StrEnum):
    """策略只观察或实际阻断。"""

    MONITOR = "monitor"
    ENFORCE = "enforce"


def lifetime_covers(granted: Lifetime, requested: Lifetime) -> bool:
    """判断授权 lifetime 是否覆盖请求 lifetime。"""
    covered: tuple[Lifetime, ...]
    match granted:
        case Lifetime.CALL:
            covered = (Lifetime.CALL,)
        case Lifetime.TASK:
            covered = (Lifetime.CALL, Lifetime.TASK)
        case Lifetime.SESSION:
            covered = (Lifetime.CALL, Lifetime.SESSION)
        case Lifetime.PERSISTENT:
            covered = tuple(Lifetime)
        case _ as unreachable:
            assert_never(unreachable)
    return requested in covered


def scope_covers(granted: Scope, requested: Scope) -> bool:
    """判断 Grant/Manifest scope 是否覆盖 Effect scope。"""
    return granted is requested
