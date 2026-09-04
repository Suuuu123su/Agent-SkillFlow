"""数据库定义和批准的阶段合同必须覆盖每次真实启动。"""

from pathlib import Path

import pytest

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.configuration import build_configuration, write_configuration
from skillflow.experiment.t17.v2.frozen import file_digest
from skillflow.experiment.t17.v2.matrix import build_matrix
from skillflow.experiment.t17.v2.stage import StageSetup, run_stage
from skillflow.experiment.t17.v2.stage_contract import freeze_phase


def test_runtime_freeze_includes_executed_database_schema(t17_cli_root: Path) -> None:
    root = Path.cwd()
    config, bundles = build_configuration(root, t17_cli_root / "freeze-config")
    write_configuration(root, t17_cli_root / "freeze-config", config, bundles)
    matrix = build_matrix(root, config, T17LiveStage.CANARY)
    phase = freeze_phase(root, config, matrix, "live_reference")
    key = "src/skillflow/store/schema.sql"
    assert phase.runtime_files[key] == file_digest(root / key)


def test_live_stage_needs_unchanged_previously_approved_phase(t17_cli_root: Path) -> None:
    root = Path.cwd()
    config, bundles = build_configuration(root, t17_cli_root / "approved-config")
    write_configuration(root, t17_cli_root / "approved-config", config, bundles)
    matrix = build_matrix(root, config, T17LiveStage.CANARY)
    phase = freeze_phase(root, config, matrix, "live_reference")
    for approved in (None, phase.model_copy(update={"runtime_files": {}})):
        with pytest.raises(ValueError, match="v2_approved_phase_missing_or_drift"):
            run_stage(
                StageSetup(
                    root,
                    t17_cli_root / "must-not-start",
                    config,
                    matrix,
                    "live_reference",
                    None,
                    approved_phase=approved,
                )
            )
    assert not (t17_cli_root / "must-not-start").exists()
