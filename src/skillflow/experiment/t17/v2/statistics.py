"""固定 10000 次簇重抽样；相同抽样权重合并计算，不改变结果。"""

import math
import random
from collections import Counter, defaultdict
from functools import lru_cache

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.v2.statistics_models import (
    MIN_CLUSTERS,
    RESAMPLES,
    SEED,
    ClusterTerm,
    StatisticalInterval,
)

Z95 = 1.959963984540054


def wilson_interval(numerator: int, denominator: int) -> StatisticalInterval:
    """链级比例的描述性区间，不解释成独立簇推断。"""
    if not 0 <= numerator <= denominator:
        raise ValueError("v2_invalid_binomial_count")
    if denominator == 0:
        return StatisticalInterval(
            status=MeasurementStatus.NOT_APPLICABLE,
            method="wilson_chain_descriptive",
            reason="没有适用链，不能把零分母写成零",
        )
    point = numerator / denominator
    divisor = 1 + Z95 * Z95 / denominator
    center = (point + Z95 * Z95 / (2 * denominator)) / divisor
    radius = (
        Z95
        * math.sqrt(point * (1 - point) / denominator + Z95 * Z95 / (4 * denominator * denominator))
        / divisor
    )
    return StatisticalInterval(
        status=MeasurementStatus.MEASURED,
        method="wilson_chain_descriptive",
        point=point,
        lower=max(0, center - radius),
        upper=min(1, center + radius),
    )


def complete_terms(
    rows: tuple[ClusterTerm, ...], signs: dict[str, int]
) -> tuple[tuple[tuple[float, float], ...], ...]:
    """每个对比项都有正分母的簇才进入配对重抽样。"""
    if not signs or any(sign not in {-1, 1} for sign in signs.values()):
        raise ValueError("v2_invalid_contrast_terms")
    grouped: dict[str, dict[str, list[float]]] = defaultdict(dict)
    for row in rows:
        if row.term not in signs:
            raise ValueError("v2_unknown_contrast_term")
        cell = grouped[row.cluster].setdefault(row.term, [0.0, 0.0])
        cell[0] += row.numerator
        cell[1] += row.denominator
    return tuple(
        tuple((cells[term][0], cells[term][1]) for term in signs)
        for _, cells in sorted(grouped.items())
        if all(term in cells and cells[term][1] > 0 for term in signs)
    )


def cluster_contrast(rows: tuple[ClusterTerm, ...], signs: dict[str, int]) -> StatisticalInterval:
    """同一组簇权重同时作用于四格或两侧；重复仅累加进簇内。"""
    cells = complete_terms(rows, signs)
    count = len(cells)
    if count < MIN_CLUSTERS:
        return StatisticalInterval(
            status=MeasurementStatus.NOT_APPLICABLE,
            method="cluster_bootstrap",
            complete_clusters=count,
            reason="少于两个完整等义表述簇，只报告描述性点值",
        )
    coefficients = tuple(signs.values())
    point = _estimate(cells, (1,) * count, coefficients)
    distribution = tuple(
        sorted(
            (_estimate(cells, weights, coefficients), frequency)
            for weights, frequency in _weights(count)
        )
    )
    return StatisticalInterval(
        status=MeasurementStatus.MEASURED,
        method="cluster_bootstrap",
        point=point,
        lower=_percentile(distribution, 0.025),
        upper=_percentile(distribution, 0.975),
        complete_clusters=count,
        resamples=RESAMPLES,
        seed=SEED,
    )


@lru_cache(maxsize=16)
def _weights(count: int) -> tuple[tuple[tuple[int, ...], int], ...]:
    generator = random.Random(SEED)  # noqa: S311 -- 固定统计重抽样，不用于秘密或随机身份。
    patterns: Counter[tuple[int, ...]] = Counter()
    for _ in range(RESAMPLES):
        selected = Counter(generator.choices(range(count), k=count))
        patterns[tuple(selected[i] for i in range(count))] += 1
    return tuple(sorted(patterns.items()))


def _estimate(
    cells: tuple[tuple[tuple[float, float], ...], ...],
    weights: tuple[int, ...],
    signs: tuple[int, ...],
) -> float:
    return sum(
        sign
        * sum(w * c[t][0] for c, w in zip(cells, weights, strict=True))
        / sum(w * c[t][1] for c, w in zip(cells, weights, strict=True))
        for t, sign in enumerate(signs)
    )


def _percentile(distribution: tuple[tuple[float, int], ...], probability: float) -> float:
    position = (RESAMPLES - 1) * probability
    lo, hi = math.floor(position), math.ceil(position)
    lower = upper = None
    consumed = 0
    for value, frequency in distribution:
        if consumed <= lo < consumed + frequency:
            lower = value
        if consumed <= hi < consumed + frequency:
            upper = value
        consumed += frequency
    if lower is None or upper is None or consumed != RESAMPLES:
        raise ValueError("v2_bootstrap_distribution_invalid")
    return lower + (position - lo) * (upper - lower)
