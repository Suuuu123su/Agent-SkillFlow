"""Scenario 独占 Workspace 的安全准备。"""

from pathlib import Path

from skillflow.instrumentation.errors import UnsupportedStepError, WorkspaceEscapeError
from skillflow.models.scenario import Scenario


def stage_assets(scenario: Scenario, workspace: Path) -> None:
    """把 fixture marker 复制到本次 Run 独占 Workspace。"""
    for asset in scenario.assets:
        prefix = "fixture://"
        if not asset.uri.root.startswith(prefix):
            raise UnsupportedStepError(asset.id, "T05 assets require fixture://")
        target = (workspace / asset.uri.root.removeprefix(prefix)).resolve()
        if not target.is_relative_to(workspace.resolve()):
            raise WorkspaceEscapeError(asset.uri.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = asset.marker if asset.marker is not None else asset.id
        target.write_text(content, encoding="utf-8")
