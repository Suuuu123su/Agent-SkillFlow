"""硬退出后区分已开始中断与确定未开始，不覆盖旧文件。"""

from pathlib import Path

import pytest
from tests.unit.experiment.t17.test_v2_live_client import FakeTransport, _client

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.configuration import build_configuration, write_configuration
from skillflow.experiment.t17.v2.interruption_records import interrupted_terminals
from skillflow.experiment.t17.v2.journal import V2UsageJournal
from skillflow.experiment.t17.v2.matrix import build_matrix
from skillflow.experiment.t17.v2.stage_contract import freeze_phase


@pytest.mark.parametrize("kind", ["core", "replay"])
def test_recovery_keeps_start_state_and_never_rewrites_source(
    t17_cli_root: Path, kind: str
) -> None:
    root = Path.cwd()
    base = t17_cli_root / ("interruption-" + kind)
    config, bundles = build_configuration(root, base / "protocol")
    write_configuration(root, base / "protocol", config, bundles)
    matrix = build_matrix(root, config, T17LiveStage.CANARY)
    phase = freeze_phase(root, config, matrix, "live_reference")
    trial = next(t for t in matrix.trials if t.replay_pair_ids)
    unit_id = trial.trial_id if kind == "core" else next(iter(trial.replay_pair_ids.values()))
    client_config = _client(base / "fixture", FakeTransport()).config.model_copy(
        update={"matrix_sha256": model_digest(matrix)}
    )
    raw = base / "raw"
    journal = V2UsageJournal(raw / "api-usage.jsonl", client_config, model_digest(phase))
    journal.begin_unit(unit_id)
    before = journal.path.read_bytes()
    records, preserved = interrupted_terminals(phase, matrix, raw, "worker_exit")
    assert not preserved
    assert len(records) == 42
    assert (
        next(r for r in records if r.identity.unit_id == unit_id).status == "infrastructure_invalid"
    )
    assert all(r.status == "not_run" for r in records if r.identity.unit_id != unit_id)
    assert journal.path.read_bytes() == before
