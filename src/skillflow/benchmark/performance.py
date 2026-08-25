"""T14 本地 EventStore 与 PolicyEngine 观察性性能基线。"""

import math
import platform
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Literal, Self

from pydantic import Field

from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import (
    CapabilityAction,
    EventType,
    Lifetime,
    PrincipalType,
    Scope,
)
from skillflow.models.events import SecurityEvent
from skillflow.models.manifest import SkillManifest
from skillflow.models.resources import ResourceRef
from skillflow.policy.engine import PolicyEngine
from skillflow.policy.models import (
    AuthorizationBoundary,
    GrantMatchRequest,
    PolicyRequest,
)
from skillflow.store.event_store import EventEnvelope
from skillflow.store.sqlite_store import SqliteEventStore

BASE_TIME = datetime(2026, 8, 25, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class PerformanceRequest:
    """一次不可跨机器比较的本地微基准请求。"""

    root: Path
    samples: int = 1_000
    warmup: int = 100


@dataclass(frozen=True, slots=True)
class PerformanceConfigurationError(Exception):
    """性能请求会覆盖证据或无法形成有效样本。"""

    detail: str

    def __str__(self) -> str:
        """返回不包含敏感输入正文的诊断。"""
        return self.detail

    @classmethod
    def database_exists(cls, database: Path) -> Self:
        """构造拒绝覆盖既有性能证据的错误。"""
        detail = f"性能数据库已存在，拒绝覆盖：{database}"
        return cls(detail)

    @classmethod
    def invalid_samples(cls) -> Self:
        """构造无有效测量样本的错误。"""
        return cls("samples 必须至少为 1")

    @classmethod
    def invalid_warmup(cls) -> Self:
        """构造负预热次数错误。"""
        return cls("warmup 不能为负数")

    @classmethod
    def event_missing(cls, event_id: str) -> Self:
        """构造 EventStore 未读回已追加事件的错误。"""
        detail = f"EventStore 未读回 {event_id}"
        return cls(detail)


class PerformanceEnvironment(StrictModel):
    """解释本地延迟所必需的运行环境。"""

    python: NonEmptyStr
    platform: NonEmptyStr
    processor: NonEmptyStr
    sqlite: NonEmptyStr


class LatencyMeasurement(StrictModel):
    """单一操作的微秒级分位数，不携带跨机器阈值。"""

    samples: int = Field(gt=0)
    minimum_us: float = Field(ge=0)
    p50_us: float = Field(ge=0)
    p95_us: float = Field(ge=0)
    maximum_us: float = Field(ge=0)


class LocalPerformanceBaseline(StrictModel):
    """T14 本机观察值；不能解释为平台无关 SLA。"""

    environment: PerformanceEnvironment
    threshold_policy: Literal["observational_baseline_only"]
    measurements: dict[str, LatencyMeasurement]


def measure_local_performance(request: PerformanceRequest) -> LocalPerformanceBaseline:
    """测量本地追加/读取与纯策略评估，不设置硬 p95 门槛。"""
    _validate_request(request)
    request.root.mkdir(parents=True, exist_ok=True)
    database = request.root / "event-store.sqlite"
    if database.exists():
        raise PerformanceConfigurationError.database_exists(database)
    append, read = _measure_event_store(database, request)
    policy = _measure_policy_engine(request)
    return LocalPerformanceBaseline(
        environment=_environment(),
        threshold_policy="observational_baseline_only",
        measurements={
            "event_store_append": _summarize(append),
            "event_store_get": _summarize(read),
            "policy_engine_evaluate": _summarize(policy),
        },
    )


def _validate_request(request: PerformanceRequest) -> None:
    if request.samples < 1:
        raise PerformanceConfigurationError.invalid_samples()
    if request.warmup < 0:
        raise PerformanceConfigurationError.invalid_warmup()


def _measure_event_store(
    database: Path,
    request: PerformanceRequest,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    append_latencies: list[int] = []
    read_latencies: list[int] = []
    with SqliteEventStore(database) as store:
        for index in range(request.warmup):
            store.append_event(EventEnvelope(_event(index)))
        offset = request.warmup
        for index in range(request.samples):
            event = _event(offset + index)
            started = time.perf_counter_ns()
            store.append_event(EventEnvelope(event))
            append_latencies.append(time.perf_counter_ns() - started)
        for index in range(request.samples):
            event_id = f"perf-event-{offset + index}"
            started = time.perf_counter_ns()
            stored_event = store.get_event(event_id)
            read_latencies.append(time.perf_counter_ns() - started)
            if stored_event is None:
                raise PerformanceConfigurationError.event_missing(event_id)
    return tuple(append_latencies), tuple(read_latencies)


def _measure_policy_engine(request: PerformanceRequest) -> tuple[int, ...]:
    engine = PolicyEngine()
    policy_request = _policy_request()
    for _ in range(request.warmup):
        engine.evaluate(policy_request)
    latencies: list[int] = []
    for _ in range(request.samples):
        started = time.perf_counter_ns()
        engine.evaluate(policy_request)
        latencies.append(time.perf_counter_ns() - started)
    return tuple(latencies)


def _event(index: int) -> SecurityEvent:
    return SecurityEvent(
        event_id=f"perf-event-{index}",
        run_id="run-t14-performance",
        task_id="task-t14-performance",
        session_id="session-t14-performance",
        timestamp=BASE_TIME + timedelta(microseconds=index),
        event_type=EventType.RUN_START,
        actor_id=PrincipalType.HARNESS.value,
    )


def _policy_request() -> PolicyRequest:
    effect = CapabilityEffect(
        source=ResourceRef("workspace:/performance/input.txt"),
        action=CapabilityAction.FILE_READ,
        sink=ResourceRef("context:/task"),
        scope=Scope.EXACT_FILE,
        lifetime=Lifetime.CALL,
        sensitivity=1,
    )
    grant = AuthorizationGrant(
        grant_id="grant-t14-performance",
        issuer_id="user-t14",
        issuer_type=PrincipalType.USER,
        grantee_id="skill-t14-performance",
        action=effect.action,
        source_pattern=effect.source,
        sink_pattern=effect.sink,
        scope=effect.scope,
        lifetime=Lifetime.TASK,
        task_id="task-t14-performance",
        valid_from=BASE_TIME,
    )
    return PolicyRequest(
        manifest=SkillManifest(
            schema_version="0.1",
            id="skill-t14-performance",
            requested_permissions=(effect,),
        ),
        grants=(grant,),
        grant_request=GrantMatchRequest(
            actor_id="skill-t14-performance",
            effect=effect,
            boundary=AuthorizationBoundary(
                task_id="task-t14-performance",
                session_id="session-t14-performance",
                call_id="call-t14-performance",
                effect_time=BASE_TIME,
            ),
        ),
    )


def _summarize(latencies_ns: tuple[int, ...]) -> LatencyMeasurement:
    ordered = tuple(sorted(value / 1_000 for value in latencies_ns))
    p95_index = math.ceil(0.95 * len(ordered)) - 1
    return LatencyMeasurement(
        samples=len(ordered),
        minimum_us=round(ordered[0], 3),
        p50_us=round(median(ordered), 3),
        p95_us=round(ordered[p95_index], 3),
        maximum_us=round(ordered[-1], 3),
    )


def _environment() -> PerformanceEnvironment:
    return PerformanceEnvironment(
        python=platform.python_version(),
        platform=platform.platform(),
        processor=platform.processor() or platform.machine() or "unknown",
        sqlite=sqlite3.sqlite_version,
    )
