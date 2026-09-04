"""第二版结构哈希：排序无序集合，保留列表和事件顺序，不改历史哈希。"""

import hashlib
import json
from dataclasses import asdict, is_dataclass

from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from skillflow.models.base import StrictModel


def canonical_text(value: object) -> str:
    """Python 的随机哈希种子不能改变相同事实的承诺。"""
    return json.dumps(
        to_jsonable_python(_ordered(value)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_digest(value: object) -> str:
    """对规范化结构计算 SHA-256，而文件清单仍散列实际字节。"""
    return hashlib.sha256(canonical_text(value).encode()).hexdigest()


def model_digest(model: StrictModel) -> str:
    """保留类型中集合与有序列表的区别，避免先转 JSON 丢掉该信息。"""
    return canonical_digest(model)


def _ordered(value: object) -> object:
    if isinstance(value, BaseModel):
        return _ordered(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return _ordered(asdict(value))
    if isinstance(value, dict):
        return {str(key): _ordered(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((_ordered(item) for item in value), key=canonical_text)
    if isinstance(value, (list, tuple)):
        return [_ordered(item) for item in value]
    return value
