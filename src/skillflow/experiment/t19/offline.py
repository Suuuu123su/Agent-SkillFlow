"""T19 export/recompute/check 命令默认完全离线，没有付费模型入口。"""

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

from pydantic import BaseModel

from skillflow.experiment.t17.v2.api_models import V2LiveConfig
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t18.catalog_models import LocalSkill
from skillflow.experiment.t19.accounting import LedgerInputs, recompute_cost
from skillflow.experiment.t19.campaign import CampaignPlan
from skillflow.experiment.t19.diagnostics import diagnose
from skillflow.experiment.t19.execution import CoreRecord
from skillflow.experiment.t19.freeze import PhaseFreeze
from skillflow.experiment.t19.metric_adapter import MetricBinding, bind_skill
from skillflow.experiment.t19.persistence import write_record
from skillflow.experiment.t19.public_facts import PublicCore, PublicReplay
from skillflow.experiment.t19.replay import ReplayRecord
from skillflow.experiment.t19.reporting import PublicIndex, T19Report, report
from skillflow.experiment.t19.usage import read_usage


def export(phase: Path, campaign: Path, live_root: Path, output: Path) -> None:
    """新目录导出；私有检查点、正文、密钥与原报告值均不复制。"""
    output.mkdir(parents=True, exist_ok=False)
    frozen = PhaseFreeze.model_validate_json((phase / "freeze.json").read_text(encoding="utf-8"))
    plan = CampaignPlan.model_validate_json((phase / "plan.json").read_text(encoding="utf-8"))
    if model_digest(plan) != frozen.plan_sha256:
        raise ValueError("t19_export_plan_binding")
    bindings = {
        k: MetricBinding.model_validate(v)
        for k, v in json.loads((phase / "metric-bindings.json").read_text(encoding="utf-8")).items()
    }
    snapshots = {
        k: LocalSkill.model_validate(v)
        for k, v in json.loads((phase / "task-snapshots.json").read_text(encoding="utf-8")).items()
    }
    if {k: model_digest(v) for k, v in snapshots.items()} != frozen.tasks or {
        k: bind_skill(v) for k, v in snapshots.items()
    } != bindings:
        raise ValueError("t19_export_task_binding")
    records = tuple(
        CoreRecord.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted((campaign / "core").glob("*.json"))
    )
    trials = {t.trial_id: t for t in plan.trials}
    _jsonl(
        output / "core-trials.jsonl",
        tuple(
            PublicCore.capture(
                trials[c.unit_id],
                bindings[
                    ":".join(  # noqa: FLY002 -- 同冻结键的元组形式。
                        (
                            trials[c.unit_id].mechanism,
                            trials[c.unit_id].role,
                            trials[c.unit_id].template,
                        )
                    )
                ],
                c,
            )
            for c in records
        ),
    )
    replays = tuple(
        ReplayRecord.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted((campaign / "audits").glob("*/*.json"))
    )
    _jsonl(output / "replay-pairs.jsonl", tuple(PublicReplay.capture(r) for r in replays))
    _jsonl(output / "intervention-traces.jsonl", tuple(t for c in records for t in c.traces))
    _jsonl(output / "diagnoses.jsonl", tuple(r for c in records for r in diagnose(c)))
    _jsonl(output / "defense-plans.jsonl", tuple(t.selection for c in records for t in c.traces))
    _jsonl(output / "recovery-records.jsonl", tuple(r for c in records for r in c.recoveries))
    _jsonl(
        output / "failure-records.jsonl",
        tuple(
            r
            for c in records
            for r in (
                *c.issues,
                *c.limits,
                *c.boundary_issues,
                *(d for d in c.decisions if d.behavior != "normal"),
            )
        ),
    )
    write_record(output / "index.json", PublicIndex(phase_sha256=model_digest(frozen), plan=plan))
    config = V2LiveConfig.model_validate_json(
        (phase / "live-config.json").read_text(encoding="utf-8")
    )
    journals = {
        p.parent.name: read_usage(p, live_root)
        for p in sorted((live_root / "attempts").glob("*/api-usage.jsonl"))
    }
    write_record(
        output / "ledger-facts.json",
        LedgerInputs(pricing=config.provider.pricing, journals=journals),
    )
    for name in ("freeze.json", "live-config.json", "metric-bindings.json"):
        (output / name).write_bytes((phase / name).read_bytes())
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.iterdir())
        if p.is_file()
    }
    (output / "SHA256.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")


def recompute(source: Path, output: Path) -> T19Report:
    """只读导出事实；不读取metrics.json或其他原报告。"""
    hashes = json.loads((source / "SHA256.json").read_text(encoding="utf-8"))
    for name, expected in hashes.items():
        path = (source / name).resolve()
        if (
            not path.is_relative_to(source.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise ValueError("t19_public_file_hash")
    index = PublicIndex.model_validate_json((source / "index.json").read_text(encoding="utf-8"))
    cores = tuple(
        PublicCore.model_validate_json(s)
        for s in (source / "core-trials.jsonl").read_text(encoding="utf-8").splitlines()
    )
    pairs = tuple(
        PublicReplay.model_validate_json(s)
        for s in (source / "replay-pairs.jsonl").read_text(encoding="utf-8").splitlines()
    )
    result = report(index, cores, pairs)
    ledger = LedgerInputs.model_validate_json(
        (source / "ledger-facts.json").read_text(encoding="utf-8")
    )
    write_record(output / "metrics.json", result)
    write_record(output / "costs.json", recompute_cost(ledger))
    _csv(
        output / "metrics-long.csv",
        tuple({"metric": k, **v.model_dump(mode="json")} for k, v in result.metrics.items()),
    )
    _csv(output / "paired-results.csv", tuple(r.model_dump(mode="json") for r in result.paired))
    _jsonl(output / "causal-audit.jsonl", result.causal)
    return result


def check(left: Path, right: Path) -> dict[str, object]:
    """两个进程独立生成后才逐项比对，费用字符串需精确相等。"""
    differences: list[str] = []

    def visit(a: object, b: object, path: str) -> None:
        if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
            for key in a:
                visit(a[key], b[key], path + "/" + str(key))
        elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            for i, (x, y) in enumerate(zip(a, b, strict=True)):
                visit(x, y, path + "/" + str(i))
        elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if not math.isclose(a, b, abs_tol=1e-12, rel_tol=1e-12):
                differences.append(path)
        elif a != b:
            differences.append(path)

    for filename in ("metrics.json", "costs.json"):
        visit(
            json.loads((left / filename).read_text(encoding="utf-8")),
            json.loads((right / filename).read_text(encoding="utf-8")),
            filename,
        )
    return {
        "status": "passed" if not differences else "failed",
        "differences": differences,
        "absolute_tolerance": 1e-12,
        "relative_tolerance": 1e-12,
    }


def _jsonl(path: Path, rows: tuple[BaseModel, ...]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(row.model_dump_json() + "\n")


def _csv(path: Path, rows: tuple[dict[str, object], ...]) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        if rows:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def _display(value: str) -> None:
    sys.stdout.write(value + "\n")


def main() -> None:
    """所有子命令离线；运行Live只能经过独立可信宿主。"""
    parser = argparse.ArgumentParser(description="T19 offline facts and metrics")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("export")
    for arg in ("phase", "campaign", "live-root", "output"):
        prepare.add_argument("--" + arg, type=Path, required=True)
    rebuild = commands.add_parser("recompute")
    rebuild.add_argument("--source", type=Path, required=True)
    rebuild.add_argument("--output", type=Path, required=True)
    compare = commands.add_parser("check")
    compare.add_argument("--left", type=Path, required=True)
    compare.add_argument("--right", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "export":
        export(args.phase, args.campaign, args.live_root, args.output)
    elif args.command == "recompute":
        result = recompute(args.source, args.output)
        _display(
            json.dumps(
                {
                    "status": result.data_status,
                    "cores": result.completed_core,
                    "audits": result.terminal_audit,
                }
            )
        )
    else:
        _display(json.dumps(check(args.left, args.right)))


if __name__ == "__main__":
    main()
