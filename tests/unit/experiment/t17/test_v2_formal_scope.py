"""正式预算不能接受用于软件集成的小矩阵。"""

from pathlib import Path

import pytest

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.configuration import build_configuration, write_configuration
from skillflow.experiment.t17.v2.formal_scope import require_full_t17
from skillflow.experiment.t17.v2.matrix import build_matrix


def test_paid_entry_rejects_small_local_test_matrix(t17_cli_root: Path) -> None:
    root = Path.cwd()
    config, bundles = build_configuration(root, t17_cli_root / "scope")
    config = config.model_copy(update={"templates": config.templates[:1], "repeats": 1})
    write_configuration(root, t17_cli_root / "scope", config, bundles)
    matrices = tuple(build_matrix(root, config, s) for s in T17LiveStage)
    with pytest.raises(ValueError, match="v2_formal_scope"):
        require_full_t17(root, config, matrices)


def test_full_scope_accepts_only_frozen_counts_and_providers(t17_cli_root: Path) -> None:
    root = Path.cwd()
    config, bundles = build_configuration(root, t17_cli_root / "full-scope")
    write_configuration(root, t17_cli_root / "full-scope", config, bundles)
    matrices = tuple(build_matrix(root, config, s) for s in T17LiveStage)
    require_full_t17(root, config, matrices)
    with pytest.raises(ValueError, match="v2_formal_scope"):
        require_full_t17(root, config, matrices[:-1])
    changed = config.model_copy(update={"model2": config.model1})
    with pytest.raises(ValueError, match="v2_formal_scope"):
        require_full_t17(root, changed, matrices)
