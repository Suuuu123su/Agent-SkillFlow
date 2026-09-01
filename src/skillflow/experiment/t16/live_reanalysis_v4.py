"""T16-C 0.4：严格绑定冻结设计并公开证据可识别下界。"""

import hashlib
import json
import os
from argparse import ArgumentParser
from collections.abc import Sequence
from pathlib import Path

from skillflow.experiment.t16.live_reanalysis_v3 import (
    LiveReanalysisPaths,
    LiveReanalysisV3Error,
    LoadedLiveReanalysisDesign,
    build_live_reanalysis_v3,
    load_live_reanalysis_design,
)
from skillflow.experiment.t16.live_reanalysis_v4_evidence import (
    LiveReanalysisV4Error,
    operational_v4,
    phase_contract_binding,
    require_record_design_fields,
    target_v4,
    unclassified_receipts,
)
from skillflow.experiment.t16.live_reanalysis_v4_models import (
    LiveDesignBindingV4,
    LiveReanalysisReportV4,
)
from skillflow.experiment.t16.live_records import LiveTrialRecord
from skillflow.experiment.t16.live_store import LiveResultStore

SOURCE_CHANGED_ERROR = "读取期间 trial-results.jsonl 发生变化，拒绝 v0.4 重分析"


class LiveReanalysisV4WriteError(OSError):
    """v0.4 报告无法以不可覆盖方式写出。"""

    __slots__ = ("detail", "path")

    def __init__(self, path: Path, detail: str) -> None:
        """保留写入路径与稳定诊断。"""
        super().__init__(detail)
        self.path = path
        self.detail = detail

    def __str__(self) -> str:
        """返回稳定文件诊断。"""
        return f"{self.path.name}: {self.detail}"


def build_live_reanalysis_v4(
    records: tuple[LiveTrialRecord, ...],
    source_trial_results_path: str,
    source_trial_results_sha256: str,
    design: LoadedLiveReanalysisDesign,
) -> LiveReanalysisReportV4:
    """逐条复核冻结设计后，从原始 audit 构造 v0.4 修正版报告。"""
    ordered = tuple(sorted(records, key=lambda item: item.result.trial_id))
    require_record_design_fields(ordered, design)
    phase_contract, limitations = phase_contract_binding(ordered)
    try:
        base = build_live_reanalysis_v3(
            ordered,
            source_trial_results_path,
            source_trial_results_sha256,
            design,
        )
    except LiveReanalysisV3Error as error:
        raise LiveReanalysisV4Error(str(error)) from error
    unclassified = unclassified_receipts(
        ordered,
        base.target_execution_authorization.unclassified_receipted_trial_ids,
    )
    target = target_v4(base.target_execution_authorization, unclassified)
    operational = operational_v4(base.operational_design_labeled_uea, unclassified)
    binding = LiveDesignBindingV4(
        **base.design_binding.model_dump(mode="python"),
        phase_contract=phase_contract,
        compatibility_limitations=limitations,
    )
    return LiveReanalysisReportV4(
        source_trial_results_path=base.source_trial_results_path,
        source_trial_results_sha256=base.source_trial_results_sha256,
        source_record_count=base.source_record_count,
        design_binding=binding,
        evidence_basis=base.evidence_basis,
        legacy_outcomes=base.legacy_outcomes,
        hiaa=base.hiaa,
        authorization_operational_rates=base.authorization_operational_rates,
        m2_operational_rates=base.m2_operational_rates,
        target_execution_authorization=target,
        operational_design_labeled_uea=operational,
        formal_uea=base.formal_uea,
        alr=base.alr,
        rir_1=base.rir_1,
        rir_3=base.rir_3,
        provenance=base.provenance,
        provenance_not_available_count=base.provenance_not_available_count,
    )


def reanalyze_live_results_v4(paths: LiveReanalysisPaths) -> LiveReanalysisReportV4:
    """复验来源字节和冻结设计，并 exclusive-create v0.4 报告。"""
    source_before = _sha256(paths.source_path)
    records = LiveResultStore(paths.source_path).read_records()
    source_after = _sha256(paths.source_path)
    if source_before != source_after:
        raise LiveReanalysisV4Error(SOURCE_CHANGED_ERROR)
    design = load_live_reanalysis_design(
        paths.preregistration_path,
        paths.matrix_path,
    )
    report = build_live_reanalysis_v4(
        records,
        paths.source_path.as_posix(),
        source_before,
        design,
    )
    _write_exclusive(paths.output_path, report)
    return report


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
    except OSError as error:
        detail = f"{path.name}: {error}"
        raise LiveReanalysisV4Error(detail) from error
    return digest.hexdigest()


def _write_exclusive(path: Path, report: LiveReanalysisReportV4) -> None:
    content = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(f"{content}\n")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise LiveReanalysisV4WriteError(path, str(error)) from error


def main(argv: Sequence[str] | None = None) -> int:
    """运行无网络且显式绑定 preregistration/Matrix 的 v0.4 CLI。"""
    parser = ArgumentParser(description="T16-C 0.4 设计绑定离线重分析")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    arguments = parser.parse_args(argv)
    reanalyze_live_results_v4(
        LiveReanalysisPaths(
            source_path=arguments.source,
            output_path=arguments.output,
            preregistration_path=arguments.preregistration,
            matrix_path=arguments.matrix,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
