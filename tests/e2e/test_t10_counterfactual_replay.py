import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from skillflow.benchmark.replay import ReplayRunner
from skillflow.benchmark.scripted_backend import (
    FixtureScript,
    InputArtifactBinding,
    InputArtifactGate,
    ToolScriptAction,
)
from skillflow.models.enums import Decision
from skillflow.models.reports import RISK_REPORT_ADAPTER, ReplayRiskReport
from skillflow.models.resources import ResourceRef
from skillflow.models.tool_calls import HttpSendArgs

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "t10"
CAUSE = b'{"enabled":true }'
IRRELEVANT = b'{"note":"stable"}'


def _runner() -> ReplayRunner:
    return ReplayRunner(
        scripts={
            "fixture://cause_producer": FixtureScript(
                output=CAUSE,
                output_mime_type="application/json",
            ),
            "fixture://irrelevant_producer": FixtureScript(
                output=IRRELEVANT,
                output_mime_type="application/json",
            ),
            "fixture://consumer": FixtureScript(
                output=b"consumer-finished",
                actions=(
                    ToolScriptAction(
                        action_id="send-trigger",
                        decision_key="allow-original",
                        arguments=HttpSendArgs(
                            source_artifact_id="artifact-placeholder",
                            source=ResourceRef("context:/trigger"),
                            sink=ResourceRef("mock://external"),
                            sensitivity=1,
                        ),
                        input_binding=InputArtifactBinding(input_index=0),
                        input_gate=InputArtifactGate(
                            input_index=0,
                            expected_content_hash=hashlib.sha256(CAUSE).hexdigest(),
                            mismatch_decision_key="deny-neutral",
                        ),
                    ),
                ),
            ),
        },
        decisions={
            "allow-original": Decision.ALLOW,
            "deny-neutral": Decision.DENY,
        },
    )


def test_t10_replay_confirms_cause_and_rejects_irrelevant_control(tmp_path: Path) -> None:
    batch = _runner().run(
        FIXTURE_ROOT / "paired_replay.yaml",
        tmp_path / "replay-a",
        seed="t10-replay-seed",
    )
    pairs = {pair.target_alias: pair for pair in batch.pairs}
    positive = pairs["cause"]
    negative = pairs["irrelevant"]

    assert positive.report.y_original is True
    assert positive.report.y_neutral is False
    assert positive.report.ci == 1
    assert len(positive.report.confirmed_influence_edges) == 1
    assert negative.report.y_original is True
    assert negative.report.y_neutral is True
    assert negative.report.ci == 0
    assert negative.report.confirmed_influence_edges == ()

    assert positive.original_restore_state_hash == positive.checkpoint.state_hash
    assert positive.neutral_restore_state_hash == positive.checkpoint.state_hash
    assert positive.original_prefix_hash == positive.neutral_prefix_hash
    assert positive.original_intervention.derived.content_length == len(CAUSE)
    assert positive.neutral_intervention.derived.content_length == len(CAUSE)
    assert (
        positive.original_intervention.derived.artifact_type
        is positive.neutral_intervention.derived.artifact_type
    )
    assert positive.original_intervention.derived.mime_type == "application/json"
    assert positive.neutral_intervention.schema_preserved
    assert (
        positive.original_intervention.derived.artifact_id
        == positive.neutral_intervention.derived.artifact_id
    )
    assert (
        positive.original_intervention.derived.content_hash
        != positive.neutral_intervention.derived.content_hash
    )
    assert positive.checkpoint.skill_state == positive.original_pre_intervention_skill_state
    assert positive.checkpoint.skill_state == positive.neutral_pre_intervention_skill_state

    schema = json.loads(Path("schemas/risk-report.schema.json").read_text(encoding="utf-8"))
    for pair in batch.pairs:
        payload = json.loads(pair.report_path.read_text(encoding="utf-8"))
        report = RISK_REPORT_ADAPTER.validate_python(payload)
        Draft202012Validator(schema).validate(payload)
        assert isinstance(report, ReplayRiskReport)
        exported = pair.report_path.read_text(encoding="utf-8") + pair.manifest_path.read_text(
            encoding="utf-8"
        )
        assert CAUSE.decode() not in exported
        assert IRRELEVANT.decode() not in exported
        assert str(tmp_path) not in exported


def test_t10_replay_is_byte_deterministic_across_fresh_roots(tmp_path: Path) -> None:
    first = _runner().run(
        FIXTURE_ROOT / "paired_replay.yaml",
        tmp_path / "replay-first",
        seed="t10-replay-seed",
    )
    second = _runner().run(
        FIXTURE_ROOT / "paired_replay.yaml",
        tmp_path / "replay-second",
        seed="t10-replay-seed",
    )

    assert tuple(pair.report_path.read_bytes() for pair in first.pairs) == tuple(
        pair.report_path.read_bytes() for pair in second.pairs
    )
    assert tuple(pair.manifest_path.read_bytes() for pair in first.pairs) == tuple(
        pair.manifest_path.read_bytes() for pair in second.pairs
    )
