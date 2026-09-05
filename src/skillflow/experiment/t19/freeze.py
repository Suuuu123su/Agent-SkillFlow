"""T19 请求前冻结：代码、任务、矩阵、预算和模型配置逐文件绑定。"""

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from skillflow.experiment.t17.v2.api_models import V2LiveConfig
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t19.campaign import CampaignPlan
from skillflow.experiment.t19.metric_adapter import bind_skill
from skillflow.experiment.t19.persistence import write_record
from skillflow.experiment.t19.tasks import task_variant
from skillflow.models.base import StrictModel


class PhaseFreeze(StrictModel):
    """配置已生成不代表已运行，Live 必须逐项复核此对象。"""

    protocol: str = "t19-rx-v1"
    phase: str
    plan_sha256: str
    live_config_sha256: str
    files: dict[str, str]
    tasks: dict[str, str]
    independent_review: str = "REVIEW_UNAVAILABLE"


def digest(path: Path) -> str:
    """内容摘要不读取凭据或环境变量。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_phase(root: Path, output: Path, plan: CampaignPlan, phase: str) -> PhaseFreeze:
    """只准备合同；没有网络调用或凭据读取。"""
    budget_path = root / "experiments/t19/budget.json"
    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    reference = root / "experiments/t19/model-reference.json"
    config = json.loads(reference.read_text(encoding="utf-8"))
    config["budget"].update(max_total_usd=budget["allocation_usd"], max_retries=0)
    config.update(
        matrix_sha256=model_digest(plan),
        cost_plan_sha256=digest(budget_path),
        approval_id="t19-user-goal-ds-v4-flash-20260905",
        max_input_bytes=12000,
    )
    live = V2LiveConfig.model_validate(config)
    paths = sorted((root / "src/skillflow").rglob("*.py"))
    paths.extend(sorted((root / "experiments/t19").glob("*.md")))
    paths.extend(sorted((root / "experiments/t19").glob("*.json")))
    paths.extend((root / "pyproject.toml", root / "experiments/t19/best-fixed.json"))
    frozen = PhaseFreeze(
        phase=phase,
        plan_sha256=model_digest(plan),
        live_config_sha256=model_digest(live),
        files={p.relative_to(root).as_posix(): digest(p) for p in paths},
        tasks=_task_digests(root, plan),
    )
    snapshots = {key: task_variant(root, *key.split(":")) for key in frozen.tasks}
    output.mkdir(parents=True, exist_ok=True)
    (output / "task-snapshots.json").write_text(
        json.dumps(
            {key: skill.model_dump(mode="json") for key, skill in snapshots.items()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (output / "metric-bindings.json").write_text(
        json.dumps(
            {key: bind_skill(skill).model_dump(mode="json") for key, skill in snapshots.items()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    write_record(output / "plan.json", plan)
    write_record(output / "live-config.json", live)
    with ZipFile(output / "code-and-contracts.zip", "x", compression=ZIP_DEFLATED) as archive:
        for relative in frozen.files:
            archive.write(root / relative, relative)
        archive.write(output / "task-snapshots.json", "phase/task-snapshots.json")
        archive.write(output / "metric-bindings.json", "phase/metric-bindings.json")
        archive.write(output / "plan.json", "phase/plan.json")
        archive.write(output / "live-config.json", "phase/live-config.json")
    write_record(output / "freeze.json", frozen)
    return frozen


def verify_phase(root: Path, directory: Path) -> tuple[PhaseFreeze, CampaignPlan, V2LiveConfig]:
    """代码或配置变化先失败，不在真实运行中静默使用新版本。"""
    frozen = PhaseFreeze.model_validate_json(
        (directory / "freeze.json").read_text(encoding="utf-8")
    )
    plan = CampaignPlan.model_validate_json((directory / "plan.json").read_text(encoding="utf-8"))
    live = V2LiveConfig.model_validate_json(
        (directory / "live-config.json").read_text(encoding="utf-8")
    )
    if model_digest(plan) != frozen.plan_sha256 or model_digest(live) != frozen.live_config_sha256:
        raise ValueError("t19_frozen_configuration_drift")
    if live.matrix_sha256 != frozen.plan_sha256:
        raise ValueError("t19_matrix_authorization_mismatch")
    if _task_digests(root, plan) != frozen.tasks:
        raise ValueError("t19_frozen_task_drift")
    for relative, expected in frozen.files.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or digest(path) != expected:
            raise ValueError("t19_frozen_file_drift:" + relative)
    return frozen, plan, live


def _task_digests(root: Path, plan: CampaignPlan) -> dict[str, str]:
    keys = sorted({(t.mechanism, t.role, t.template) for t in plan.trials})
    return {":".join(key): model_digest(task_variant(root, *key)) for key in keys}
