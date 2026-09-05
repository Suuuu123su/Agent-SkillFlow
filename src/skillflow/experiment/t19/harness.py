"""T19 结构化控制字段的离线干预及保留数据的桥梁关闭。"""

import json
from collections.abc import Callable
from dataclasses import replace

from skillflow.adapters.base import SkillInvocation, SkillInvocationResult
from skillflow.adapters.live_reference_harness import LiveReferenceHarnessAdapter
from skillflow.instrumentation.artifact_intervention import (
    ArtifactInterventionMode,
    ArtifactInterventionResult,
)
from skillflow.models.enums import EventType
from skillflow.runtime.session import ActorCall, ArtifactEmission

from .neutralization import neutralize_control


class RxHarnessAdapter(LiveReferenceHarnessAdapter):
    """继承原始沙盒和回执；Skill 无权调用这里的干预接口。"""

    bridge_data_only: bool = False
    derivation_observer: Callable[[str, str], None] | None = None

    def benchmark_intervene_artifact(
        self, source_artifact_id: str, mode: ArtifactInterventionMode
    ) -> ArtifactInterventionResult:
        """原视图和中和分支均追加新版本，原Artifact不可改写。"""
        recorder = self._require_runtime("t19_intervene").recorder
        source = recorder.require_artifact(source_artifact_id)
        content = recorder.read_content(source_artifact_id)
        changed = (
            content if mode is ArtifactInterventionMode.IDENTITY else neutralize_control(content)
        )
        derived = recorder.record_artifact(
            ArtifactEmission(
                event_type=EventType.ARTIFACT_DERIVE,
                artifact_type=source.artifact_type,
                content=changed,
                actor=ActorCall("harness:counterfactual", None),
                input_artifact_ids=(source_artifact_id,),
                origins=source.observed_label.origins,
                trust=source.observed_label.trust,
                mime_type=source.mime_type,
                metadata={"intervention": mode.value, "contract": "t19-facts-control-v1"},
            )
        )
        if self.derivation_observer is not None:
            self.derivation_observer(source_artifact_id, derived.artifact_id)
        return ArtifactInterventionResult(mode, source, derived, schema_preserved=True)

    def invoke_skill(self, invocation: SkillInvocation) -> SkillInvocationResult:
        """关闭的仅是跨技能控制字段，合法facts及原始来源仍可达。"""
        if not self.bridge_data_only:
            return super().invoke_skill(invocation)
        recorder = self._require_runtime("t19_data_bridge").recorder
        inputs = []
        for identifier in invocation.input_artifact_ids:
            content = recorder.read_content(identifier)
            if not content:
                # A failed model generation contains neither facts nor control to bridge.
                inputs.append(identifier)
                continue
            try:
                value = json.loads(content)
            except (ValueError, UnicodeDecodeError) as error:
                raise ValueError("t19_bridge_control_not_losslessly_separable") from error
            if value is None or isinstance(value, (bool, int, float)):
                # A JSON scalar is usable data and contains no structured control field.
                inputs.append(identifier)
                continue
            if isinstance(value, dict) and set(value) == {"facts", "control"}:
                derived = self.benchmark_intervene_artifact(
                    identifier, ArtifactInterventionMode.NEUTRAL
                )
                inputs.append(derived.derived.artifact_id)
            else:
                raise ValueError("t19_bridge_control_not_losslessly_separable")
        return super().invoke_skill(replace(invocation, input_artifact_ids=tuple(inputs)))
