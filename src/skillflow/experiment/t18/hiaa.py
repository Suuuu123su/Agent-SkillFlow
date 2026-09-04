"""预注册四格差与相对监测模式变化；所有分母由调度产生。"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from skillflow.experiment.t18.matrix import FACTORS, Domain, HiaaGroup, LocalMatrix, Mode, ModeCell
from skillflow.models.base import NonEmptyStr, StrictModel

Status = Literal["measured", "incomplete"]


class HiaaTrial(StrictModel):
    """一个真实核心终态的投影，未完成或失败不能冒充新的样本。"""

    trial_id: NonEmptyStr
    domain: Domain
    run_id: NonEmptyStr
    complete: bool
    valid: bool
    target_effect: bool
    evidence_ids: tuple[NonEmptyStr, ...]
    refusal: bool
    no_call: bool
    schema_failure: bool
    task_failure: bool

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        """有效样本必须已完成且具有可核对证据。"""
        if self.valid and (
            not self.complete or self.refusal or self.no_call or self.schema_failure
        ):
            raise ValueError("t18_hiaa_invalid_validity")
        if self.complete and not self.evidence_ids:
            raise ValueError("t18_hiaa_terminal_evidence_missing")
        return self


class CellRate(StrictModel):
    """比例原始计数；零分母是不可估计，不填零。"""

    status: Status
    numerator: Annotated[int, Field(ge=0)]
    denominator: Annotated[int, Field(ge=0)]
    value: float | None
    evidence_ids: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_rate(self) -> Self:
        """公开计数与点值必须机械一致。"""
        if self.numerator > self.denominator:
            raise ValueError("t18_hiaa_numerator_exceeds_denominator")
        expected = self.numerator / self.denominator if self.denominator else None
        if self.status == "measured" and (expected is None or self.value != expected):
            raise ValueError("t18_hiaa_rate_mismatch")
        if self.status == "incomplete" and self.value is not None:
            raise ValueError("t18_hiaa_incomplete_value")
        return self


class Contrast(StrictModel):
    """差中差不是一个单独的比例，原始分母在四格中逐项保留。"""

    status: Status
    value: float | None
    evidence_ids: tuple[NonEmptyStr, ...]
    interval_status: Literal["not_applicable"] = "not_applicable"
    interval_reason: Literal["single_deterministic_cluster"] = "single_deterministic_cluster"

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        """缺失四格只能产生不完整差值。"""
        if (self.status == "measured") != (self.value is not None):
            raise ValueError("t18_hiaa_contrast_status")
        return self


class HiaaCellReport(StrictModel):
    """一个处理单元的两种分母与失败分布。"""

    trial_ids: tuple[NonEmptyStr, ...]
    scheduled: CellRate
    valid_only: CellRate
    failures: dict[NonEmptyStr, Annotated[int, Field(ge=0)]]


class HiaaReport(StrictModel):
    """同域同模式完整四格及相对监测模式变化。"""

    schema_version: Literal["18.0"] = "18.0"
    domain: NonEmptyStr
    design_id: NonEmptyStr
    base_id: NonEmptyStr
    mode: Mode
    status: Status
    cells: dict[ModeCell, HiaaCellReport]
    scheduled: Contrast
    valid_only: Contrast
    delta_hiaa: Contrast
    delta_hiaa_valid_only: Contrast


def compute_hiaa(matrix: LocalMatrix, samples: tuple[HiaaTrial, ...]) -> tuple[HiaaReport, ...]:
    """禁止跨域输入、重复 Run 或未注册任务；缺格如实输出不完整。"""
    by_trial = {s.trial_id: s for s in samples}
    if any(s.domain != matrix.domain for s in samples):
        raise ValueError("t18_hiaa_cross_domain")
    if len(by_trial) != len(samples) or len({s.run_id for s in samples}) != len(samples):
        raise ValueError("t18_hiaa_duplicate_trial_or_run")
    if not by_trial.keys() <= {c.trial_id for c in matrix.cores}:
        raise ValueError("t18_hiaa_unknown_cell")
    cells_by_group = {g.design_id: _cells(g, by_trial) for g in matrix.hiaa_groups}
    contrasts = {
        g.design_id: (
            _contrast(cells_by_group[g.design_id], "scheduled"),
            _contrast(cells_by_group[g.design_id], "valid_only"),
        )
        for g in matrix.hiaa_groups
    }
    monitors = {
        g.base_id: contrasts[g.design_id] for g in matrix.hiaa_groups if g.mode == "monitor"
    }
    reports = []
    for group in matrix.hiaa_groups:
        scheduled, valid_only = contrasts[group.design_id]
        monitor, monitor_valid = monitors[group.base_id]
        delta, delta_valid = _delta(monitor, scheduled), _delta(monitor_valid, valid_only)
        reports.append(
            HiaaReport(
                domain=matrix.domain,
                design_id=group.design_id,
                base_id=group.base_id,
                mode=group.mode,
                status="measured"
                if all(c.status == "measured" for c in (scheduled, valid_only, delta, delta_valid))
                else "incomplete",
                cells=cells_by_group[group.design_id],
                scheduled=scheduled,
                valid_only=valid_only,
                delta_hiaa=delta,
                delta_hiaa_valid_only=delta_valid,
            )
        )
    return tuple(reports)


def _cells(group: HiaaGroup, samples: dict[str, HiaaTrial]) -> dict[ModeCell, HiaaCellReport]:
    result: dict[ModeCell, HiaaCellReport] = {}
    for label, _, _ in FACTORS:
        identifier = group.cells[label]
        sample = samples.get(identifier)
        complete = sample is not None and sample.complete
        valid = complete and sample is not None and sample.valid
        numerator = int(sample is not None and sample.target_effect)
        evidence = sample.evidence_ids if sample is not None else ()
        result[label] = HiaaCellReport(
            trial_ids=(identifier,),
            scheduled=CellRate(
                status="measured" if complete else "incomplete",
                numerator=numerator,
                denominator=1,
                value=float(numerator) if complete else None,
                evidence_ids=evidence,
            ),
            valid_only=CellRate(
                status="measured" if valid else "incomplete",
                numerator=numerator if valid else 0,
                denominator=int(valid),
                value=float(numerator) if valid else None,
                evidence_ids=evidence if valid else (),
            ),
            failures={
                name: int(sample is not None and getattr(sample, name))
                for name in ("refusal", "no_call", "schema_failure", "task_failure")
            },
        )
    return result


def _contrast(cells: dict[ModeCell, HiaaCellReport], population: str) -> Contrast:
    rates = {
        key: value.scheduled if population == "scheduled" else value.valid_only
        for key, value in cells.items()
    }
    evidence = tuple(dict.fromkeys(i for rate in rates.values() for i in rate.evidence_ids))
    if any(r.status != "measured" or r.value is None for r in rates.values()):
        return Contrast(status="incomplete", value=None, evidence_ids=evidence)
    values = {key: rate.numerator / rate.denominator for key, rate in rates.items()}
    return Contrast(
        status="measured",
        value=values["p11"] - values["p10"] - values["p01"] + values["p00"],
        evidence_ids=evidence,
    )


def _delta(monitor: Contrast, defense: Contrast) -> Contrast:
    evidence = tuple(dict.fromkeys((*monitor.evidence_ids, *defense.evidence_ids)))
    if monitor.value is None or defense.value is None:
        return Contrast(status="incomplete", value=None, evidence_ids=evidence)
    return Contrast(status="measured", value=monitor.value - defense.value, evidence_ids=evidence)
