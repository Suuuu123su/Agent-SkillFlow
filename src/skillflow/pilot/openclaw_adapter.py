"""真实 OpenClaw Driver 与统一观察之间的隔离 Adapter。"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from skillflow.models.events import SecurityEvent
from skillflow.models.metrics import MetricStatus, RatioMetric
from skillflow.pilot.errors import OpenClawPilotError
from skillflow.pilot.models import (
    EFFECT_KINDS,
    OpenClawRawEvent,
    PilotAdapterKind,
    PilotEffectEvidence,
    PilotObservation,
    ProvenanceBasis,
)
from skillflow.pilot.openclaw_events import load_openclaw_events, translate_openclaw_events
from skillflow.pilot.openclaw_plan import compile_openclaw_plan
from skillflow.pilot.openclaw_plan_models import OpenClawScenarioPlan


class OpenClawDriver(Protocol):
    """允许用内存 Fake 测试 Adapter，而不在单元测试启动 Gateway。"""

    def execute(self, plan: OpenClawScenarioPlan, output_root: Path) -> Path:
        """返回观察插件 JSONL 路径。"""
        ...


@dataclass(frozen=True, slots=True)
class NodeOpenClawDriver:
    """只用参数数组启动固定 OpenClaw Driver，不经过 Shell。"""

    node_path: Path
    openclaw_root: Path
    driver_path: Path
    plugin_path: Path
    timeout_seconds: int = 900

    def execute(self, plan: OpenClawScenarioPlan, output_root: Path) -> Path:
        """写入严格请求并运行隔离 Gateway。"""
        output_root.parent.mkdir(parents=True, exist_ok=True)
        request_path = output_root.parent / f"{output_root.name}-request.json"
        try:
            with request_path.open("x", encoding="utf-8") as stream:
                stream.write(plan.model_dump_json(indent=2) + "\n")
        except FileExistsError as error:
            raise OpenClawPilotError.request_exists(str(request_path)) from error
        process = subprocess.run(  # noqa: S603 - T15 explicitly authorizes the pinned driver.
            (
                str(self.node_path),
                "--import",
                "tsx",
                str(self.driver_path),
                "--request",
                str(request_path),
                "--output",
                str(output_root),
                "--plugin",
                str(self.plugin_path),
            ),
            cwd=self.openclaw_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        if process.returncode != 0:
            detail = process.stderr[-4000:] or process.stdout[-4000:] or "no driver output"
            raise OpenClawPilotError.driver_failed(process.returncode, detail)
        return output_root / "openclaw-events.jsonl"


@dataclass(frozen=True, slots=True)
class OpenClawPilotAdapter:
    """执行同一 Scenario，并拒绝把缺失平台事实补写成授权。"""

    driver: OpenClawDriver

    def run(self, scenario_path: Path, output_root: Path) -> PilotObservation:
        """编译、执行、严格解析并输出统一 SecurityEvent。"""
        plan = compile_openclaw_plan(scenario_path)
        raw_events = load_openclaw_events(self.driver.execute(plan, output_root))
        events = translate_openclaw_events(raw_events)
        target_aliases = frozenset(plan.target_effect_aliases)
        target_raw = tuple(
            item
            for item in raw_events
            if item.kind in EFFECT_KINDS and item.effect_alias in target_aliases
        )
        effects = tuple(_effect(item) for item in target_raw)
        expected = frozenset(plan.expected_origin_ids)
        matching = tuple(
            item.receipt_id
            for item in target_raw
            if expected.issubset(item.origin_ids) and item.receipt_id is not None
        )
        recall = _ratio(len(matching), len(target_raw), matching)
        missing = ["grant_matcher", "artifact_provenance_graph"]
        if plan.revocations:
            missing.append("skill_revocation_hook")
        _write_security_events(output_root / "security-events.jsonl", events)
        observation = PilotObservation(
            adapter=PilotAdapterKind.OPENCLAW,
            scenario_id=plan.scenario_id,
            security_events=events,
            target_effects=effects,
            provenance_recall=recall,
            provenance_basis=ProvenanceBasis.TARGET_EFFECT_LABELS,
            missing_hooks=tuple(missing),
        )
        with (output_root / "observation.json").open("x", encoding="utf-8") as stream:
            stream.write(observation.model_dump_json(indent=2) + "\n")
        return observation


def _effect(raw: OpenClawRawEvent) -> PilotEffectEvidence:
    if (
        raw.effect_alias is None
        or raw.action is None
        or raw.receipt_id is None
        or raw.policy_fact is None
    ):
        raise OpenClawPilotError.target_evidence_incomplete()
    return PilotEffectEvidence(
        effect_alias=raw.effect_alias,
        action=raw.action,
        receipt_id=raw.receipt_id,
        origin_ids=raw.origin_ids,
        policy_fact=raw.policy_fact,
    )


def _ratio(numerator: int, denominator: int, evidence: tuple[str, ...]) -> RatioMetric:
    if denominator == 0:
        return RatioMetric(
            numerator=0,
            denominator=0,
            value=None,
            status=MetricStatus.NOT_APPLICABLE,
        )
    return RatioMetric(
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator,
        status=MetricStatus.DEFINED,
        evidence_ids=evidence,
    )


def _write_security_events(path: Path, events: tuple[SecurityEvent, ...]) -> None:
    payload = "\n".join(
        json.dumps(event.model_dump(mode="json"), ensure_ascii=True, sort_keys=True)
        for event in events
    )
    with path.open("x", encoding="utf-8") as stream:
        stream.write(payload + "\n")
