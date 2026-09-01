"""OpenAI Responses API 所需的严格最小数据模型。"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from skillflow.experiment.t16.openai_output_schemas import (
    ResponseOutputContract,
    response_output_schema,
)
from skillflow.experiment.t16.provider import ReasoningEffort
from skillflow.models.base import NonEmptyStr, StrictModel

JsonObject = dict[str, JsonValue]
CACHE_BREAKDOWN_ERROR = "cache read and write input exceeds input"
REASONING_BREAKDOWN_ERROR = "reasoning output exceeds output"


class ApiModel(BaseModel):
    """解析所需 API 字段；未知字段不进入内部记录。"""

    model_config = ConfigDict(extra="ignore", frozen=True)


class InputTokenDetails(ApiModel):
    """输入 token 的缓存读取和缓存写入拆分。"""

    cached_tokens: Annotated[int, Field(ge=0)]
    cache_write_tokens: Annotated[int, Field(ge=0)] = 0


class OutputTokenDetails(ApiModel):
    """输出 token 中由 reasoning 消耗的部分。"""

    reasoning_tokens: Annotated[int, Field(ge=0)]


class ApiUsage(ApiModel):
    """Responses API 的完整用量对象。"""

    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    total_tokens: Annotated[int, Field(ge=0)]
    input_tokens_details: InputTokenDetails
    output_tokens_details: OutputTokenDetails

    @model_validator(mode="after")
    def require_valid_breakdown(self) -> Self:
        """缓存与 reasoning 子项都不能超过各自总数。"""
        cached = self.input_tokens_details.cached_tokens
        cache_write = self.input_tokens_details.cache_write_tokens
        if cached + cache_write > self.input_tokens:
            raise ValueError(CACHE_BREAKDOWN_ERROR)
        if self.output_tokens_details.reasoning_tokens > self.output_tokens:
            raise ValueError(REASONING_BREAKDOWN_ERROR)
        return self


class ApiFunctionCall(ApiModel):
    """模型返回的一次函数调用。"""

    type: Literal["function_call"]
    id: NonEmptyStr
    call_id: NonEmptyStr
    name: NonEmptyStr
    arguments: str
    status: str | None = None


class ApiOutputText(ApiModel):
    """模型返回的结构化文本内容块。"""

    type: Literal["output_text"]
    text: str
    annotations: tuple[JsonValue, ...] = ()


class ApiRefusal(ApiModel):
    """模型返回的拒绝内容块。"""

    type: Literal["refusal"]
    refusal: str


ApiMessageContent = Annotated[ApiOutputText | ApiRefusal, Field(discriminator="type")]


class ApiMessage(ApiModel):
    """模型返回的 assistant 消息。"""

    type: Literal["message"]
    id: NonEmptyStr
    status: str | None = None
    role: Literal["assistant"]
    content: tuple[ApiMessageContent, ...]


class ApiReasoning(ApiModel):
    """无状态续传所需的 reasoning 输出项。"""

    type: Literal["reasoning"]
    id: NonEmptyStr
    summary: tuple[JsonValue, ...] = ()
    encrypted_content: str | None = None
    status: str | None = None


ApiOutputItem = Annotated[
    ApiFunctionCall | ApiMessage | ApiReasoning,
    Field(discriminator="type"),
]


class ApiResponse(ApiModel):
    """T16-C 需要解析的 Responses 成功响应闭包。"""

    id: NonEmptyStr
    model: NonEmptyStr
    status: NonEmptyStr
    output: tuple[ApiOutputItem, ...]
    usage: ApiUsage


class OpenAIResponsesCall(StrictModel):
    """一次无凭据、可记录的 Responses 请求。"""

    model: NonEmptyStr
    temperature: Annotated[float, Field(ge=0, le=2)] | None
    reasoning_effort: ReasoningEffort
    max_output_tokens: Annotated[int, Field(ge=1)]
    input_items: Annotated[tuple[JsonObject, ...], Field(min_length=1)]
    tools: tuple[JsonObject, ...] = ()
    output_contract: ResponseOutputContract = ResponseOutputContract.FINISH_V2
    prompt_cache_mode: Literal["explicit", "automatic"] = "explicit"

    def payload(self) -> JsonObject:
        """构造固定的无状态、禁并行 Tool 请求。"""
        payload: JsonObject = {
            "model": self.model,
            "input": list(self.input_items),
            "tools": list(self.tools),
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "reasoning": {"effort": self.reasoning_effort.value},
            "max_output_tokens": self.max_output_tokens,
            "store": False,
            "include": ["reasoning.encrypted_content"],
            "truncation": "disabled",
            "text": {"format": response_output_schema(self.output_contract)},
        }
        if self.prompt_cache_mode == "explicit":
            payload["prompt_cache_options"] = {"mode": "explicit"}
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        return payload
