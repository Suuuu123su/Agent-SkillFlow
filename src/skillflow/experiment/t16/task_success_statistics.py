"""按语义实例聚类的 Bootstrap 与描述性 Wilson 区间。"""

import math
import random
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field

from skillflow.models.base import StrictModel

UnitInterval = Annotated[float, Field(ge=0, le=1)]
MIN_CLUSTER_COUNT = 2
MIN_BOOTSTRAP_RESAMPLES = 10_000
NEGATIVE_CLUSTER_TOTAL = "cluster total 不能为负"
INVALID_CLUSTER_SUCCESS = "cluster success 必须位于 [0,total]"
INVALID_PAIRED_COUNTS = "paired cluster 计数无效"
INVALID_WILSON_COUNTS = "Wilson 计数无效"
ZERO_HIAA_DENOMINATOR = "HIAA bootstrap cell 分母不能为0"
TOO_FEW_CLUSTERS = "cluster bootstrap 至少需要2个语义实例"
TOO_FEW_RESAMPLES = "cluster bootstrap 不得少于10,000次"


class ConfidenceInterval(StrictModel):
    """固定 95% 双侧区间。"""

    confidence_level: Annotated[float, Field(ge=0.95, le=0.95)] = 0.95
    lower: float
    upper: float
    method: Literal["cluster_percentile_bootstrap", "wilson_score"]


class BootstrapEstimate(StrictModel):
    """点估计及以语义实例为 cluster 的区间。"""

    point_estimate: float
    interval: ConfidenceInterval
    cluster_count: int
    resamples: int
    seed: int


@dataclass(frozen=True, slots=True)
class ClusterRateCounts:
    """一个语义实例中 HIAA 四格的全部 repeat 计数。"""

    cluster_id: str
    successes: tuple[int, int, int, int]
    totals: tuple[int, int, int, int]

    def __post_init__(self) -> None:
        """验证四格计数的基本边界。"""
        if any(total < 0 for total in self.totals):
            raise ValueError(NEGATIVE_CLUSTER_TOTAL)
        if any(
            success < 0 or success > total
            for success, total in zip(
                self.successes,
                self.totals,
                strict=True,
            )
        ):
            raise ValueError(INVALID_CLUSTER_SUCCESS)


@dataclass(frozen=True, slots=True)
class PairedClusterCounts:
    """一个语义实例内 target/control 的全部 repeat 计数。"""

    cluster_id: str
    target_successes: int
    target_total: int
    control_successes: int
    control_total: int

    def __post_init__(self) -> None:
        """验证 target/control 均有合法分母。"""
        pairs = (
            (self.target_successes, self.target_total),
            (self.control_successes, self.control_total),
        )
        if any(total <= 0 or success < 0 or success > total for success, total in pairs):
            raise ValueError(INVALID_PAIRED_COUNTS)


@dataclass(frozen=True, slots=True)
class BootstrapRun:
    """一次 bootstrap 输出所需的固定规模与随机协议。"""

    cluster_count: int
    resamples: int
    seed: int


def wilson_interval(successes: int, total: int) -> ConfidenceInterval:
    """计算链级描述性 Wilson 95% CI；不冒充 cluster-adjusted 推断。"""
    if total <= 0 or successes < 0 or successes > total:
        raise ValueError(INVALID_WILSON_COUNTS)
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    lower = 0.0 if successes == 0 else max(0.0, center - margin)
    upper = 1.0 if successes == total else min(1.0, center + margin)
    return ConfidenceInterval(
        lower=lower,
        upper=upper,
        method="wilson_score",
    )


def bootstrap_hiaa_interval(
    clusters: tuple[ClusterRateCounts, ...],
    resamples: int,
    seed: int,
) -> BootstrapEstimate:
    """每次抽取完整语义实例，并重新计算 pooled 四格率。"""
    _require_bootstrap_inputs(len(clusters), resamples)
    point = _hiaa_for_clusters(clusters)
    rng = random.Random(seed)  # noqa: S311 - 统计重采样需要可复现，不用于安全随机数。
    draws = tuple(
        _hiaa_for_clusters(tuple(rng.choice(clusters) for _ in clusters)) for _ in range(resamples)
    )
    return _bootstrap_estimate(
        point,
        draws,
        BootstrapRun(cluster_count=len(clusters), resamples=resamples, seed=seed),
    )


def bootstrap_paired_difference_interval(
    clusters: tuple[PairedClusterCounts, ...],
    resamples: int,
    seed: int,
) -> BootstrapEstimate:
    """以语义实例为配对 cluster 重算 target-control 差值。"""
    _require_bootstrap_inputs(len(clusters), resamples)
    point = _paired_difference(clusters)
    rng = random.Random(seed)  # noqa: S311 - 统计重采样需要可复现，不用于安全随机数。
    draws = tuple(
        _paired_difference(tuple(rng.choice(clusters) for _ in clusters)) for _ in range(resamples)
    )
    return _bootstrap_estimate(
        point,
        draws,
        BootstrapRun(cluster_count=len(clusters), resamples=resamples, seed=seed),
    )


def _hiaa_for_clusters(clusters: tuple[ClusterRateCounts, ...]) -> float:
    successes = tuple(sum(item.successes[index] for item in clusters) for index in range(4))
    totals = tuple(sum(item.totals[index] for item in clusters) for index in range(4))
    if any(total == 0 for total in totals):
        raise ValueError(ZERO_HIAA_DENOMINATOR)
    p00, p01, p10, p11 = tuple(
        success / total for success, total in zip(successes, totals, strict=True)
    )
    return p11 - p10 - p01 + p00


def _paired_difference(clusters: tuple[PairedClusterCounts, ...]) -> float:
    target_successes = sum(item.target_successes for item in clusters)
    target_total = sum(item.target_total for item in clusters)
    control_successes = sum(item.control_successes for item in clusters)
    control_total = sum(item.control_total for item in clusters)
    return target_successes / target_total - control_successes / control_total


def _bootstrap_estimate(
    point: float,
    draws: tuple[float, ...],
    run: BootstrapRun,
) -> BootstrapEstimate:
    ordered = tuple(sorted(draws))
    return BootstrapEstimate(
        point_estimate=point,
        interval=ConfidenceInterval(
            lower=_percentile(ordered, 0.025),
            upper=_percentile(ordered, 0.975),
            method="cluster_percentile_bootstrap",
        ),
        cluster_count=run.cluster_count,
        resamples=run.resamples,
        seed=run.seed,
    )


def _percentile(values: tuple[float, ...], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _require_bootstrap_inputs(cluster_count: int, resamples: int) -> None:
    if cluster_count < MIN_CLUSTER_COUNT:
        raise ValueError(TOO_FEW_CLUSTERS)
    if resamples < MIN_BOOTSTRAP_RESAMPLES:
        raise ValueError(TOO_FEW_RESAMPLES)
