import json
import socket
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from pydantic import JsonValue, SecretStr

from skillflow.experiment.t16 import live_cli
from skillflow.experiment.t16.live_campaign_report import LiveCampaignReportError
from skillflow.experiment.t16.live_cli import LiveCampaignRequest, run_live_campaign
from skillflow.experiment.t16.openai_response_models import JsonObject
from skillflow.experiment.t16.openai_responses import ResponsesTransport, TransportResponse

ROOT = Path(__file__).parents[2]
UNEXPECTED_NETWORK = "unexpected real network"


class FinalOnlyTransport(ResponsesTransport):
    def __init__(self) -> None:
        self.calls = 0

    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: JsonObject,
    ) -> TransportResponse:
        assert url == "https://api.openai.com/v1/responses"
        assert payload["model"] == "gpt-5.6-luna"
        assert headers["authorization"].startswith("Bearer ")
        self.calls += 1
        final: dict[str, JsonValue] = {
            "status": "completed",
            "summary": "mock campaign",
        }
        body: JsonObject = {
            "id": f"resp-{self.calls}",
            "model": "gpt-5.6-luna",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "id": f"msg-{self.calls}",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": json.dumps(final)}],
                }
            ],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 5},
            },
        }
        return TransportResponse(200, body, 1)


def test_full_campaign_uses_mock_transport_and_never_opens_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FinalOnlyTransport()

    @contextmanager
    def mock_transport() -> Iterator[ResponsesTransport]:
        yield transport

    def forbidden_socket(*_args: object, **_kwargs: object) -> socket.socket:
        raise AssertionError(UNEXPECTED_NETWORK)

    monkeypatch.setattr(live_cli, "managed_httpx2_transport", mock_transport)
    monkeypatch.setattr(socket, "socket", forbidden_socket)
    output_root = tmp_path / "campaign"
    marker_text = str(uuid.UUID(int=12345))

    result = run_live_campaign(
        LiveCampaignRequest(ROOT, output_root),
        SecretStr(marker_text),
    )

    assert result.smoke.completed_trial_count == 48
    assert result.model1 is not None
    assert result.model1.completed_trial_count == 360
    assert result.metrics is not None
    assert result.metrics.schema_version == "0.4"
    assert result.metrics.source_record_count == 360
    assert result.metrics.design_binding.expected_trial_count == 360
    assert result.metrics.design_binding.expected_trial_ids == (
        result.metrics.design_binding.observed_trial_ids
    )
    assert result.metrics.design_binding.unique_model_input_count == 110
    assert len(result.metrics.design_binding.model_input_manifest_sha256) == 64
    assert result.metrics.design_binding.phase_contract.status == "available"
    assert result.metrics.design_binding.phase_contract.sha256 is not None
    assert result.metrics.evidence_basis.m2_execution_basis == (
        "per_session_expected_alias_tool_audit"
    )
    assert result.metrics.evidence_basis.compatibility_limitations == ()
    assert result.metrics.research_conclusion_eligible is False
    assert transport.calls == 612
    report_path = output_root / "model1" / "metrics-reanalysis-v0.4.json"
    assert report_path.is_file()
    assert not (output_root / "model1" / "metrics-reanalysis-v0.2.json").exists()
    assert not (output_root / "model1" / "metrics-reanalysis-v0.3.json").exists()
    assert not (output_root / "model1" / "metrics-report.json").exists()
    report_before_resume = report_path.read_bytes()

    resumed = run_live_campaign(
        LiveCampaignRequest(ROOT, output_root, resume=True),
        SecretStr(marker_text),
    )

    assert resumed.metrics == result.metrics
    assert report_path.read_bytes() == report_before_resume
    assert transport.calls == 612

    mismatched_payload = json.loads(report_before_resume)
    mismatched_payload["source_trial_results_sha256"] = "0" * 64
    report_path.write_text(
        f"{json.dumps(mismatched_payload, ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )
    mismatched_report = report_path.read_bytes()
    with pytest.raises(LiveCampaignReportError, match="证据/设计复算不一致"):
        run_live_campaign(
            LiveCampaignRequest(ROOT, output_root, resume=True),
            SecretStr(marker_text),
        )
    assert report_path.read_bytes() == mismatched_report
    assert transport.calls == 612
    persisted = "\n".join(path.read_text(encoding="utf-8") for path in output_root.rglob("*.json*"))
    assert marker_text not in persisted
