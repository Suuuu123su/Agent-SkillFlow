"""仅开发集枚举8种固定组件组合；选择过程不访问正式样本。"""

import itertools
import json
from pathlib import Path
from typing import TypedDict

from skillflow.defense.rx import ORDER, Component
from skillflow.experiment.t19.execution import CoreRecord, ExecutionSetup, execute
from skillflow.experiment.t19.tasks import task_variant


class DevelopmentRow(TypedDict):
    """未合成权重的开发选择计数。"""

    components: tuple[Component, ...]
    task_success: int
    safe_success: int
    risk_chains: int
    checks: int
    count: int
    tie_bits: tuple[bool, ...]


CONDITIONS = (
    ("C1", "attack"),
    ("C1", "neutral"),
    ("C2", "attack"),
    ("C2", "neutral"),
    ("M2", "attack"),
    ("M2", "neutral"),
    ("A1", "attack"),
    ("A1", "neutral"),
    ("B0", "control"),
    ("N0", "control"),
    ("G0", "control"),
    ("A2", "control"),
    ("B1", "attack"),
    ("S1", "attack"),
    ("L1", "attack"),
)


def run_development(
    root: Path,
    output: Path,
    *,
    repair_source: Path | None = None,
    repair_conditions: tuple[tuple[str, str], ...] = (("A1", "neutral"),),
) -> dict[str, object]:
    """独占新记录；已完成项只读取，不重执行。此入口不能调用真实API。"""
    output.mkdir(parents=True, exist_ok=True)
    rows: list[DevelopmentRow] = []
    for bits in itertools.product((False, True), repeat=3):
        components: tuple[Component, ...] = tuple(
            c for c, enabled in zip(ORDER, bits, strict=True) if enabled
        )
        label = "".join(components) or "G"
        records = []
        for base, role in CONDITIONS:
            unit_id = "dev-" + label + "-" + base.lower() + "-" + role
            terminal = output / (unit_id + ".json")
            inherited = repair_source / terminal.name if repair_source else None
            if inherited is not None and (base, role) not in repair_conditions:
                record = CoreRecord.model_validate_json(inherited.read_text(encoding="utf-8"))
            elif terminal.exists():
                record = CoreRecord.model_validate_json(terminal.read_text(encoding="utf-8"))
            else:
                skill = task_variant(root, base, role, "development")
                record, _ = execute(
                    ExecutionSetup(
                        root, output / "raw", unit_id, "scripted", "Best Fixed", components
                    ),
                    skill,
                    None,
                )
                with terminal.open("x", encoding="utf-8") as stream:
                    stream.write(record.model_dump_json() + "\n")
            records.append(record)
        task = sum(r.data.proof.task.task_success for r in records)
        risk = sum(bool(r.data.proof.task.risk_effect_ids) for r in records)
        safe = sum(
            r.data.proof.task.task_success and not r.data.proof.task.risk_effect_ids
            for r in records
        )
        checks = sum(len(t.interventions) for r in records for t in r.traces)
        rows.append(
            {
                "components": components,
                "task_success": task,
                "safe_success": safe,
                "risk_chains": risk,
                "checks": checks,
                "count": len(records),
                "tie_bits": bits,
            }
        )
    best = max(
        rows,
        key=lambda r: (
            r["safe_success"],
            r["task_success"],
            -r["risk_chains"],
            -r["checks"],
            r["tie_bits"],
        ),
    )
    result: dict[str, object] = {
        "domain": "scripted",
        "api_calls": 0,
        "research_samples": 120,
        "components": best["components"],
        "rows": rows,
        "selection_split": "development_only",
        "not_stochastic_model_upper_bound": True,
        "repair_source": str(repair_source) if repair_source else None,
        "new_executions": len(repair_conditions) * 8 if repair_source else 120,
        "inherited_executions": 120 - len(repair_conditions) * 8 if repair_source else 0,
        "repair_scope": "A1 neutral claim matches attack control hash only"
        if repair_source
        else None,
    }
    with (output / "best-fixed.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result
