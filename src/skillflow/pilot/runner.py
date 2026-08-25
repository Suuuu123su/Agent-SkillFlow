"""T15 三场景、双 Adapter Pilot 的不可覆盖编排。"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from skillflow.pilot.errors import PilotRunError
from skillflow.pilot.mock_adapter import MockPilotAdapter
from skillflow.pilot.models import PilotReport
from skillflow.pilot.openclaw_adapter import NodeOpenClawDriver, OpenClawPilotAdapter
from skillflow.pilot.orchestrator import run_pilot_pair

OPENCLAW_COMMIT: Final = "452e734022214f5f00bdd44cae675cc467c3cd85"
PILOT_SCENARIOS: Final = (
    Path("scenarios/benign/b0_legal_summary.yaml"),
    Path("scenarios/benign/g0_legal_cross_skill.yaml"),
    Path("scenarios/attacks/m2_revoked_memory_residual.yaml"),
)


@dataclass(frozen=True, slots=True)
class PilotRunRequest:
    """一次隔离 T15 Pilot 所需的所有本地路径。"""

    project_root: Path
    openclaw_root: Path
    output_root: Path
    node_path: Path
    git_path: Path


def execute_t15_pilot(request: PilotRunRequest) -> PilotReport:
    """验证 OpenClaw pin，并在两个 Adapter 上运行三个相同 Scenario。"""
    if request.output_root.exists():
        raise PilotRunError.output_exists(str(request.output_root))
    actual_commit = openclaw_revision(request.openclaw_root, request.git_path)
    require_pinned_commit(actual_commit)
    integration_root = request.project_root / "integrations" / "openclaw"
    driver = NodeOpenClawDriver(
        node_path=request.node_path,
        openclaw_root=request.openclaw_root,
        driver_path=integration_root / "driver.ts",
        plugin_path=integration_root / "skillflow-observer",
    )
    mock = MockPilotAdapter()
    openclaw = OpenClawPilotAdapter(driver)
    comparisons = tuple(
        run_pilot_pair(
            request.project_root / scenario,
            request.output_root / scenario.stem,
            mock,
            openclaw,
        )
        for scenario in PILOT_SCENARIOS
    )
    report = PilotReport(
        openclaw_commit=actual_commit,
        comparisons=comparisons,
        real_credentials_used=False,
        external_effects_replaced=True,
        production_state_modified=False,
    )
    with (request.output_root / "pilot-report.json").open("x", encoding="utf-8") as stream:
        stream.write(report.model_dump_json(indent=2) + "\n")
    return report


def openclaw_revision(openclaw_root: Path, git_path: Path) -> str:
    """通过参数数组读取被审计 OpenClaw checkout 的精确 revision。"""
    try:
        process = subprocess.run(  # noqa: S603 - fixed git operation, no shell.
            (str(git_path), "rev-parse", "HEAD"),
            cwd=openclaw_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except OSError as error:
        raise PilotRunError.git_failed(str(error)) from error
    actual = process.stdout.strip()
    if process.returncode != 0 or not actual:
        detail = process.stderr.strip() or "git rev-parse 未返回 revision"
        raise PilotRunError.git_failed(detail)
    return actual


def require_pinned_commit(actual: str) -> None:
    """拒绝对未审计的 OpenClaw revision 运行真实 Harness。"""
    if actual != OPENCLAW_COMMIT:
        raise PilotRunError.commit_mismatch(actual, OPENCLAW_COMMIT)
