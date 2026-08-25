"""可注入的虚拟时钟与确定性 ID 边界。"""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """提供当前时间的可注入合同。"""

    def now(self) -> datetime:
        """返回当前时间。"""
        ...


class IdFactory(Protocol):
    """提供命名空间隔离 ID 的可注入合同。"""

    def new_id(self, namespace: str) -> str:
        """生成下一个确定性 ID。"""
        ...


@dataclass(frozen=True, slots=True)
class VirtualClockSnapshot:
    """Checkpoint 中的精确虚拟时间。"""

    current: datetime


@dataclass(frozen=True, slots=True)
class DeterministicIdSnapshot:
    """ID seed 与各命名空间下一计数。"""

    seed: str
    counters: tuple[tuple[str, int], ...]


class VirtualClock:
    """由测试显式推进的虚拟时钟。"""

    def __init__(self, start: datetime) -> None:
        """以调用方提供的固定时间初始化。"""
        self._current = start

    def now(self) -> datetime:
        """返回当前虚拟时间且不隐式推进。"""
        return self._current

    def advance(self, delta: timedelta) -> None:
        """按调用方指定增量推进虚拟时间。"""
        self._current += delta

    def snapshot(self) -> VirtualClockSnapshot:
        """冻结当前虚拟时间。"""
        return VirtualClockSnapshot(self._current)

    def restore(self, snapshot: VirtualClockSnapshot) -> None:
        """恢复到 checkpoint 的精确虚拟时间。"""
        self._current = snapshot.current


class DeterministicIdFactory:
    """由 seed 和计数器生成稳定 ID 的工厂。"""

    def __init__(self, seed: str) -> None:
        """保存 seed 并初始化命名空间计数器。"""
        self._seed = seed
        self._counters: dict[str, int] = {}

    def new_id(self, namespace: str) -> str:
        """生成同 seed、同调用序列下可重放的 ID。"""
        counter = self._counters.get(namespace, 0)
        material = f"{self._seed}:{namespace}:{counter}".encode()
        digest = hashlib.sha256(material).hexdigest()[:16]
        self._counters[namespace] = counter + 1
        return f"{namespace}-{digest}"

    def snapshot(self) -> DeterministicIdSnapshot:
        """按命名空间排序冻结全部计数器。"""
        return DeterministicIdSnapshot(self._seed, tuple(sorted(self._counters.items())))

    def restore(self, snapshot: DeterministicIdSnapshot) -> None:
        """恢复 seed 与全部命名空间计数器。"""
        self._seed = snapshot.seed
        self._counters = dict(snapshot.counters)
