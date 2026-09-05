from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from skillflow.experiment.t19 import host
from skillflow.experiment.t19.campaign import CampaignPlan
from skillflow.experiment.t19.freeze import prepare_phase
from skillflow.experiment.t19.host import HostJob, HostStatus, worker
from skillflow.experiment.t19.matrix import precheck

from .test_t19_live import LocalTransport


class LocalChannel:
    def __init__(self, job: HostJob) -> None:
        self.inputs = iter(
            (b"unique-test-credential-should-never-be-written", job.model_dump_json().encode())
        )
        self.messages: list[bytes] = []

    def recv_bytes(self) -> bytes:
        return next(self.inputs)

    def send_bytes(self, data: bytes) -> None:
        self.messages.append(data)

    def close(self) -> None:
        pass


def test_missing_freeze_stops_before_network_and_never_exports_key(tmp_path: Path) -> None:
    live = tmp_path / "live"
    job = HostJob(
        root=tmp_path,
        live_root=live,
        phase_directory=tmp_path / "missing",
        output_directory=live / "precheck",
        attempt_id="attempt-01",
    )
    channel = LocalChannel(job)
    worker(channel)
    result = HostStatus.model_validate_json(channel.messages[-1])
    assert result.status == "failed"
    assert result.reason == "FileNotFoundError"
    assert result.api_calls == 0
    assert all(b"unique-test-credential" not in p.read_bytes() for p in tmp_path.rglob("*.json"))


@pytest.mark.parametrize("identifier", ["../other", "C:\\other", "a/b", "a:b", ""])
def test_attempt_id_cannot_escape_output(tmp_path: Path, identifier: str) -> None:
    with pytest.raises(ValidationError):
        HostJob(
            root=tmp_path,
            live_root=tmp_path,
            phase_directory=tmp_path,
            output_directory=tmp_path,
            attempt_id=identifier,
        )


def test_trusted_host_reads_key_once_and_skips_completed_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    live = tmp_path / "live"
    (live / "jobs").mkdir(parents=True)
    (live / "job-results").mkdir()
    for index in range(3):
        job = HostJob(
            root=tmp_path,
            live_root=live,
            phase_directory=tmp_path / "phase",
            output_directory=live / f"output-{index}",
            attempt_id=f"attempt-{index}",
        )
        (live / "jobs" / f"{index:03d}.json").write_text(job.model_dump_json(), encoding="utf-8")
    (live / "job-results/000.json").write_text("{}", encoding="utf-8")
    reads: list[str] = []
    executed: list[str] = []

    def key_reader(prompt: str) -> str:
        reads.append(prompt)
        return "main-test-only"

    class StubKeeper:
        def __init__(self, secret: SecretStr) -> None:
            assert secret.get_secret_value() == "main-test-only"

        def execute(self, payload: bytes, *_arguments: object) -> SimpleNamespace:
            executed.append(HostJob.model_validate_json(payload).attempt_id)
            return SimpleNamespace(reason=None)

    monkeypatch.setattr(host.getpass, "getpass", key_reader)
    monkeypatch.setattr(host, "MemoryKeyKeeper", StubKeeper)
    monkeypatch.setattr(
        host.sys, "argv", ["host", "--root", str(tmp_path), "--live-root", str(live)]
    )
    monkeypatch.setattr(host.time, "sleep", lambda _: (live / "stop-host").write_text("stop"))
    host.main()
    assert len(reads) == 1
    assert executed == ["attempt-1", "attempt-2"]
    assert len(tuple((live / "job-results").glob("*.json"))) == 3
    assert "main-test-only" not in capsys.readouterr().out
    assert all(b"main-test-only" not in p.read_bytes() for p in live.rglob("*.json"))


@pytest.mark.parametrize("outside_project", [False, True])
def test_invalid_worker_output_does_not_write_a_failure_outside_boundary(
    tmp_path: Path, outside_project: bool
) -> None:
    root = tmp_path / "owned"
    output = tmp_path / "outside" if outside_project else root / "not-live"
    job = HostJob(
        root=root,
        live_root=root / "live",
        phase_directory=root / "phase",
        output_directory=output,
        attempt_id="invalid-path-test",
    )
    channel = LocalChannel(job)
    worker(channel)
    status = HostStatus.model_validate_json(channel.messages[-1])
    assert status.reason == "ValueError"
    assert status.api_calls == 0
    assert not output.exists()


def test_valid_worker_uses_only_local_transport_and_closes_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).resolve().parents[3]
    trial = next(t for t in precheck() if t.mechanism == "B0" and t.group == "Monitor")
    plan = CampaignPlan(domain="live_reference", fixed=("T",), trials=(trial,), audit_aliases={})
    prepare_phase(root, tmp_path / "phase", plan, "local-worker-validation")
    transport = LocalTransport()
    monkeypatch.setattr(host, "managed_transport", lambda _: nullcontext(transport))
    job = HostJob(
        root=root,
        live_root=tmp_path,
        phase_directory=tmp_path / "phase",
        output_directory=tmp_path / "output",
        attempt_id="local-worker-test",
    )
    channel = LocalChannel(job)
    worker(channel)
    status = HostStatus.model_validate_json(channel.messages[-1])
    assert status.status == "completed"
    assert status.api_calls == status.responses == transport.calls == 1
    assert any(HostStatus.model_validate_json(m).status == "running" for m in channel.messages)
    assert all(b"unique-test-credential" not in p.read_bytes() for p in tmp_path.rglob("*.json"))
