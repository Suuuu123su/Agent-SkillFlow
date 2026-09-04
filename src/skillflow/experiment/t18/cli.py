"""T18 的四个本地入口；报告与诊断不会触发实验或模型请求。"""

import json
from pathlib import Path
from typing import Annotated

import typer

from skillflow.defense.models import AttackSignalVector
from skillflow.defense.router import EvidenceDefenseRouter
from skillflow.experiment.t18.dataset import export_dataset, recompute_dataset
from skillflow.experiment.t18.report_data import load_run
from skillflow.experiment.t18.stage import load_inputs, run_batch
from skillflow.experiment.t18.tables import recompute_collection
from skillflow.validation import DocumentValidationError

app = typer.Typer(help="本地多技能诊断、防御与可复算实验。", no_args_is_help=True)


@app.command("catalog")
def catalog_command(
    root: Annotated[Path, typer.Option(help="项目根目录。")],
) -> None:
    """列出已固定的技能与模式，不生成新配置。"""
    try:
        config, _, catalog = load_inputs(root, "scripted")
    except (OSError, ValueError, DocumentValidationError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "skills": [
                    {"id": s.skill_variant_id, "role": s.role, "split": s.split}
                    for s in catalog.skills
                ],
                "scripted_core": len(config.scripted.cores),
                "fake_core": len(config.fake_reference.cores),
            },
            ensure_ascii=False,
        )
    )


@app.command("diagnose")
def diagnose_command(
    signals: Annotated[Path, typer.Option(help="可信信号 JSON，不接受场景标签。")],
) -> None:
    """只对已保存的可信信号作规则诊断，不执行防御。"""
    try:
        value = AttackSignalVector.model_validate_json(signals.read_text(encoding="utf-8"))
        diagnosis, plan = EvidenceDefenseRouter().route(value)
    except (OSError, ValueError, DocumentValidationError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {"diagnosis": diagnosis.model_dump(mode="json"), "plan": plan.model_dump(mode="json")},
            ensure_ascii=False,
        )
    )


@app.command("run-matrix")
def run_matrix_command(
    root: Annotated[Path, typer.Option(help="项目根目录。")],
    output: Annotated[Path, typer.Option(help="项目内新的 t18- 开头运行目录。")],
    domain: Annotated[str, typer.Option(help="scripted 或 fake_reference。")],
    maximum_cores: Annotated[int, typer.Option(help="本批最多 48 个；已完成记录不会重跑。")] = 24,
) -> None:
    """运行一个固定短批次，绝不扩大矩阵或自动增加重复。"""
    if domain not in {"scripted", "fake_reference"}:
        raise typer.BadParameter("t18_unknown_domain")
    try:
        result = run_batch(
            root, output, "scripted" if domain == "scripted" else "fake_reference", maximum_cores
        )
    except (OSError, ValueError, DocumentValidationError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(json.dumps(result, ensure_ascii=False))


@app.command("report")
def report_command(
    output: Annotated[Path, typer.Option(help="新导出目录或独立复算目录。")],
    dataset: Annotated[Path | None, typer.Option(help="仅从本公开数据目录独立复算。")] = None,
    run: Annotated[Path | None, typer.Option(help="读取现有本地运行并导出公开集合。")] = None,
    root: Annotated[Path | None, typer.Option(help="仅导出运行时需要项目根目录。")] = None,
) -> None:
    """二选一：导出现有事实，或不依赖私有记录的独立复算。"""
    if (dataset is None) == (run is None) or (run is not None and root is None):
        raise typer.BadParameter("t18_choose_dataset_or_run_with_root")
    try:
        if dataset is not None:
            recompute = (
                recompute_collection
                if (dataset / "sha256-manifest.json").is_file()
                else recompute_dataset
            )
            typer.echo(json.dumps(recompute(dataset, output), ensure_ascii=False))
        elif root is not None and run is not None:
            result = export_dataset(load_run(root, run), output)
            typer.echo(
                json.dumps(
                    {
                        "domain": result.domain,
                        "cores": result.core_count,
                        "replays": result.replay_count,
                    }
                )
            )
    except (OSError, ValueError, DocumentValidationError) as error:
        raise typer.BadParameter(str(error)) from error


def register_defense_commands(parent: typer.Typer) -> None:
    """保持原命令不变，注册独立的本地防御组。"""
    parent.add_typer(app, name="defense")
