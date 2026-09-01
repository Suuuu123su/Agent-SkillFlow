"""T16-C 仅产生本地证据的封闭 Tool 运行时。"""

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum, unique

from pydantic import ValidationError

from skillflow.experiment.t16.openai_response_models import JsonObject
from skillflow.experiment.t16.task_success_facts import (
    PlatformReceiptRecord,
    ReceiptRegistrationRequest,
)
from skillflow.models.base import NonEmptyStr, StrictModel

NEGATIVE_SESSION_INDEX = "session_index 不能为负数"
PLATFORM_SESSION_UNBOUND = "平台 Receipt Hook 尚未绑定 Session"


@unique
class LiveToolName(StrEnum):
    """真实模型实验可见的唯一 Tool 名集合。"""

    READ_ASSET = "read_asset"
    WRITE_MEMORY = "write_memory"
    READ_MEMORY = "read_memory"
    SAFE_EFFECT = "skillflow_safe_effect"


class ReadAssetArguments(StrictModel):
    """读取 Trial 内存资产的严格参数。"""

    asset_id: NonEmptyStr


class WriteMemoryArguments(StrictModel):
    """写入 Trial 内存的严格参数。"""

    memory_key: NonEmptyStr
    content: NonEmptyStr


class ReadMemoryArguments(StrictModel):
    """读取 Trial 内存的严格参数。"""

    memory_key: NonEmptyStr


class SafeEffectArguments(StrictModel):
    """本地安全 Effect 的严格参数。"""

    effect_alias: NonEmptyStr
    content: NonEmptyStr


@dataclass(frozen=True, slots=True)
class LiveToolSchemaError(ValueError):
    """模型 Tool 名或参数未通过封闭 Schema。"""

    tool_name: str

    def __str__(self) -> str:
        """返回不回显参数内容的稳定错误。"""
        return f"Tool Schema 拒绝: {self.tool_name}"


@dataclass(frozen=True, slots=True)
class UnknownEffectAliasError(ValueError):
    """模型请求了未预注册的 Effect。"""

    effect_alias: str

    def __str__(self) -> str:
        """返回稳定别名诊断。"""
        return f"未注册 Effect: {self.effect_alias}"


@dataclass(frozen=True, slots=True)
class LiveToolLookupError(ValueError):
    """模型读取了 Trial 运行时不存在的本地对象。"""

    object_id: str

    def __str__(self) -> str:
        """返回稳定本地对象诊断。"""
        return f"本地对象不存在: {self.object_id}"


@dataclass(frozen=True, slots=True)
class LiveToolResult:
    """可回传给模型且不包含 provenance 的 Tool 结果。"""

    tool_name: LiveToolName
    output: str
    effect_alias: str | None = None
    receipt_id: str | None = None


class LiveToolRuntime:
    """每条 Trial 独享的纯内存资产、记忆与安全 Effect 容器。"""

    def __init__(
        self,
        run_nonce: str,
        assets: dict[str, str],
        effect_alias_catalog: dict[str, str],
        platform_run_id: str | None = None,
    ) -> None:
        """复制 Trial 私有输入，避免跨 Trial 共享可变状态。"""
        self._run_nonce = run_nonce
        self._assets = dict(assets)
        self._effect_alias_catalog = dict(effect_alias_catalog)
        self._active_public_effect_aliases: frozenset[str] = frozenset()
        self._platform_run_id = platform_run_id
        self._active_session_id: str | None = None
        self._memory: dict[str, str] = {}
        self._effect_receipts: list[str] = []
        self._platform_receipts: list[PlatformReceiptRecord] = []

    @property
    def effect_receipts(self) -> tuple[str, ...]:
        """返回已经在本地生成的不可变 Receipt 列表。"""
        return tuple(self._effect_receipts)

    @property
    def memory_keys(self) -> tuple[str, ...]:
        """返回当前 Trial 中存在的记忆键。"""
        return tuple(sorted(self._memory))

    @property
    def platform_receipts(self) -> tuple[PlatformReceiptRecord, ...]:
        """返回平台 Hook 生成且不含正文的 Receipt 记录。"""
        return tuple(self._platform_receipts)

    def activate_session(self, session_index: int) -> None:
        """把后续平台 Receipt 绑定到当前真实执行 Session。"""
        if session_index < 0:
            raise ValueError(NEGATIVE_SESSION_INDEX)
        self._active_session_id = f"session-{session_index}"

    def activate_effect_aliases(self, public_aliases: frozenset[str]) -> None:
        """只为即将执行的 Session 激活其公共 Effect 别名。"""
        unknown = public_aliases.difference(self._effect_alias_catalog)
        if unknown:
            raise UnknownEffectAliasError(min(unknown))
        self._active_public_effect_aliases = public_aliases

    def execute(self, tool_name: str, arguments_json: str) -> LiveToolResult:
        """严格解析一次模型 Tool 调用；任何额外字段均拒绝。"""
        try:
            name = LiveToolName(tool_name)
            match name:
                case LiveToolName.READ_ASSET:
                    read_asset = ReadAssetArguments.model_validate_json(arguments_json)
                    return self._read_asset(read_asset)
                case LiveToolName.WRITE_MEMORY:
                    write_memory = WriteMemoryArguments.model_validate_json(arguments_json)
                    return self._write_memory(write_memory)
                case LiveToolName.READ_MEMORY:
                    read_memory = ReadMemoryArguments.model_validate_json(arguments_json)
                    return self._read_memory(read_memory)
                case LiveToolName.SAFE_EFFECT:
                    safe_effect = SafeEffectArguments.model_validate_json(arguments_json)
                    return self._safe_effect(safe_effect)
        except (ValidationError, ValueError) as error:
            if isinstance(error, (UnknownEffectAliasError, LiveToolLookupError)):
                raise
            raise LiveToolSchemaError(tool_name) from error

    def _read_asset(self, arguments: ReadAssetArguments) -> LiveToolResult:
        content = self._assets.get(arguments.asset_id)
        if content is None:
            raise LiveToolLookupError(arguments.asset_id)
        return LiveToolResult(
            LiveToolName.READ_ASSET,
            _compact_json({"content": content}),
        )

    def _write_memory(self, arguments: WriteMemoryArguments) -> LiveToolResult:
        self._memory[arguments.memory_key] = arguments.content
        return LiveToolResult(
            LiveToolName.WRITE_MEMORY,
            _compact_json({"written": True}),
        )

    def _read_memory(self, arguments: ReadMemoryArguments) -> LiveToolResult:
        content = self._memory.get(arguments.memory_key)
        if content is None:
            raise LiveToolLookupError(arguments.memory_key)
        return LiveToolResult(
            LiveToolName.READ_MEMORY,
            _compact_json({"content": content}),
        )

    def _safe_effect(self, arguments: SafeEffectArguments) -> LiveToolResult:
        actual_alias = self._effect_alias_catalog.get(arguments.effect_alias)
        if actual_alias is None or arguments.effect_alias not in self._active_public_effect_aliases:
            raise UnknownEffectAliasError(actual_alias or arguments.effect_alias)
        receipt_id = self._new_receipt(actual_alias, arguments.content.encode("utf-8"))
        self._effect_receipts.append(receipt_id)
        return LiveToolResult(
            LiveToolName.SAFE_EFFECT,
            _compact_json({"executed": True, "sink": "local-receipt-only"}),
            effect_alias=actual_alias,
            receipt_id=receipt_id,
        )

    def _new_receipt(self, effect_alias: str, payload: bytes) -> str:
        if self._platform_run_id is not None:
            if self._active_session_id is None:
                raise ValueError(PLATFORM_SESSION_UNBOUND)
            receipt = PlatformReceiptRecord.create(
                ReceiptRegistrationRequest(
                    run_id=self._platform_run_id,
                    session_id=self._active_session_id,
                    effect_alias=effect_alias,
                    receipt_ordinal=len(self._platform_receipts),
                ),
                payload=payload,
            )
            self._platform_receipts.append(receipt)
            return receipt.receipt_id
        material = f"{self._run_nonce}:{len(self._effect_receipts)}:{effect_alias}"
        digest = hashlib.sha256(material.encode()).hexdigest()[:24]
        return f"receipt-{digest}"


def live_tool_definitions(tool_names: tuple[str, ...]) -> tuple[JsonObject, ...]:
    """生成严格函数 Schema；调用参数从不开放 origin_ids。"""
    definitions = {
        LiveToolName.READ_ASSET: _tool_definition(
            LiveToolName.READ_ASSET,
            "读取当前 Trial 内预置的授权资产。",
            {"asset_id": {"type": "string"}},
        ),
        LiveToolName.WRITE_MEMORY: _tool_definition(
            LiveToolName.WRITE_MEMORY,
            "写入仅当前 Trial 可见的内存。",
            {
                "memory_key": {"type": "string"},
                "content": {"type": "string"},
            },
        ),
        LiveToolName.READ_MEMORY: _tool_definition(
            LiveToolName.READ_MEMORY,
            "读取仅当前 Trial 可见的内存。",
            {"memory_key": {"type": "string"}},
        ),
        LiveToolName.SAFE_EFFECT: _tool_definition(
            LiveToolName.SAFE_EFFECT,
            "模拟工作流 Effect，只生成本地 Receipt，不访问真实外部系统。",
            {
                "effect_alias": {"type": "string"},
                "content": {"type": "string"},
            },
        ),
    }
    try:
        names = tuple(LiveToolName(item) for item in tool_names)
    except ValueError as error:
        raise LiveToolSchemaError(str(error)) from error
    return tuple(definitions[item] for item in names)


def _tool_definition(
    name: LiveToolName,
    description: str,
    properties: JsonObject,
) -> JsonObject:
    return {
        "type": "function",
        "name": name.value,
        "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
            "required": list(properties),
        },
    }


def _compact_json(value: JsonObject) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
