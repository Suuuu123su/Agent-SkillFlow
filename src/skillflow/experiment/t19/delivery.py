"""完整离线交付视图，将预注册分层明细与主报告一起复算。"""

import hashlib
import json
from pathlib import Path

from skillflow.experiment.t19.accounting import LedgerInputs, recompute_cost
from skillflow.experiment.t19.detail_views import DetailReport, details
from skillflow.experiment.t19.integrity import verify
from skillflow.experiment.t19.offline import _csv, check, export, recompute
from skillflow.experiment.t19.persistence import write_record
from skillflow.experiment.t19.public_facts import PublicCore, PublicReplay
from skillflow.experiment.t19.reporting import PublicIndex, T19Report
from skillflow.experiment.t19.source_certificates import SourceCertificates, collect


def recompute_all(source: Path, output: Path) -> T19Report:
    """主结果和所有明细均只读事实；先前报告不能参与生成。"""
    hashes = json.loads((source / "SHA256-complete.json").read_text(encoding="utf-8"))
    for name, expected in hashes.items():
        file = (source / name).resolve()
        if (
            not file.is_relative_to(source.resolve())
            or hashlib.sha256(file.read_bytes()).hexdigest() != expected
        ):
            raise ValueError("t19_complete_export_hash")
    main = recompute(source, output / "frozen-v1")
    index = PublicIndex.model_validate_json((source / "index.json").read_text(encoding="utf-8"))
    cores = tuple(
        PublicCore.model_validate_json(s)
        for s in (source / "core-trials.jsonl").read_text(encoding="utf-8").splitlines()
    )
    pairs = tuple(
        PublicReplay.model_validate_json(s)
        for s in (source / "replay-pairs.jsonl").read_text(encoding="utf-8").splitlines()
    )
    ledger = LedgerInputs.model_validate_json(
        (source / "ledger-facts.json").read_text(encoding="utf-8")
    )
    certificates = SourceCertificates.model_validate_json(
        (source / "source-certificates.json").read_text(encoding="utf-8")
    )
    integrity = verify(index, cores, pairs, ledger, certificates)
    write_record(output / "integrity.json", integrity)
    if integrity.status != "passed":
        raise ValueError("t19_export_integrity_failed")
    detail = details(index, cores, pairs, ledger)
    write_record(output / "details.json", detail)
    combined = dict(main.metrics)
    for key, value in detail.metrics.items():
        if key in combined and combined[key] != value and key not in detail.metric_corrections:
            raise ValueError("t19_metric_view_disagreement")
        combined[key] = value
    final = main.model_copy(update={"metrics": combined})
    write_record(output / "metrics.json", final)
    write_record(output / "costs.json", recompute_cost(ledger))
    _csv(output / "paired-results.csv", tuple(r.model_dump(mode="json") for r in final.paired))
    _csv(
        output / "all-metrics-long.csv",
        tuple({"metric": k, **v.model_dump(mode="json")} for k, v in sorted(combined.items())),
    )
    for category, markers in {
        "hiaa": ("hiaa/",),
        "alr-rir": ("/A1/", "/M2/"),
        "provenance": ("provenance",),
        "diagnosis": ("diagnosis/",),
        "router-comparison": ("paired/",),
        "failure-coverage": ("failure", "coverage"),
        "cost-latency": ("cost.", "latency.", "confirmation."),
    }.items():
        rows = tuple(
            {"metric": k, **v.model_dump(mode="json")}
            for k, v in sorted(combined.items())
            if any(marker in k for marker in markers)
        )
        _csv(output / (category + ".csv"), rows)
    return final


def check_all(left: Path, right: Path) -> dict[str, object]:
    """比较发生在两个独立生成目录之后，包含全部分层明细。"""
    result = check(left, right)
    a = DetailReport.model_validate_json((left / "details.json").read_text(encoding="utf-8"))
    b = DetailReport.model_validate_json((right / "details.json").read_text(encoding="utf-8"))
    if a != b:
        result = {**result, "status": "failed", "detail_views_equal": False}
    else:
        result["detail_views_equal"] = True
    return result


def save_check(left: Path, right: Path, output: Path) -> dict[str, object]:
    """比对记录独占写入；失败记录不能由后续通过覆盖。"""
    result = check_all(left, right)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def export_all(phase: Path, campaign: Path, live_root: Path, output: Path) -> None:
    """在原事实导出上附加受信源结构证书与完整文件清单。"""
    export(phase, campaign, live_root, output)
    pairs = tuple(
        PublicReplay.model_validate_json(s)
        for s in (output / "replay-pairs.jsonl").read_text(encoding="utf-8").splitlines()
    )
    write_record(output / "source-certificates.json", collect(campaign, pairs))
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.iterdir())
        if p.is_file()
    }
    (output / "SHA256-complete.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
