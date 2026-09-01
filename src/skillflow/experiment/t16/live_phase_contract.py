"""T16-C 付费阶段恢复所绑定的完整、确定性执行合同。"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.t16.live_config import T16CLiveConfig
from skillflow.experiment.t16.live_design import build_live_trial_design
from skillflow.experiment.t16.live_run_models import LivePhase
from skillflow.experiment.t16.matrix import T16Matrix
from skillflow.experiment.t16.preregistration_models import T16Preregistration
from skillflow.models.manifest import SkillManifest
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document

_LIVE_EXECUTION_SOURCES = (
    "budget.py",
    "httpx2_transport.py",
    "live_agent.py",
    "live_agent_calls.py",
    "live_agent_session.py",
    "live_cli.py",
    "live_config.py",
    "live_design.py",
    "live_design_base.py",
    "live_design_context.py",
    "live_design_models.py",
    "live_phase_contract.py",
    "live_prompt_text.py",
    "live_record_builders.py",
    "live_records.py",
    "live_run.py",
    "live_run_models.py",
    "live_session_records.py",
    "live_store.py",
    "live_tools.py",
    "matrix.py",
    "openai_response_models.py",
    "openai_responses.py",
    "preregistration.py",
    "preregistration_models.py",
    "provider.py",
    "trial.py",
)


@dataclass(frozen=True, slots=True)
class LivePhaseContractInputs:
    """阶段合同哈希所覆盖的完整已验证输入。"""

    project_root: Path
    phase: LivePhase
    config: T16CLiveConfig
    registration: T16Preregistration
    matrix: T16Matrix
    scenarios: dict[str, Scenario]


def build_phase_contract_sha256(inputs: LivePhaseContractInputs) -> str:
    """绑定完整设计、已验证输入与执行源码，拒绝部分恢复时混合合同。"""
    payload = {
        "schema_version": "0.1",
        "phase": inputs.phase.value,
        "effective_live_config": inputs.config.model_dump(mode="json"),
        "live_config_file_sha256": _file_sha256(
            inputs.project_root / "experiments" / "t16" / "t16c_live.yaml"
        ),
        "preregistration": inputs.registration.model_dump(mode="json"),
        "matrix": inputs.matrix.model_dump(mode="json"),
        "scenarios": {
            condition_id: inputs.scenarios[condition_id].model_dump(mode="json")
            for condition_id in sorted(inputs.scenarios)
        },
        "manifests": _verified_manifests(inputs.project_root, inputs.registration),
        "compiled_trial_inputs": _compiled_trial_inputs(inputs),
        "execution_source_sha256": _execution_source_hashes(inputs.project_root),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _verified_manifests(
    project_root: Path,
    registration: T16Preregistration,
) -> dict[str, object]:
    references = sorted(
        {
            reference.root
            for condition in registration.conditions
            for reference in condition.capability.manifest_paths
        }
    )
    return {
        reference: validate_yaml_document(
            project_root / reference,
            SkillManifest,
        ).model_dump(mode="json")
        for reference in references
    }


def _compiled_trial_inputs(inputs: LivePhaseContractInputs) -> dict[str, object]:
    """把完整 Matrix 的每条盲测输入和实际 alias 清单纳入单一阶段合同。"""
    compiled: dict[str, object] = {}
    for spec in inputs.matrix.trials:
        design = build_live_trial_design(
            inputs.registration,
            spec,
            inputs.scenarios[spec.condition_id],
        )
        compiled[spec.trial_id] = {
            "model_input_sha256": hashlib.sha256(
                design.serialized_model_input().encode()
            ).hexdigest(),
            "target_effect_aliases": design.target_effect_aliases,
            "session_target_effect_aliases": {
                str(session.session_index): session.expected_target_effect_aliases
                for session in design.sessions
            },
        }
    return compiled


def _execution_source_hashes(project_root: Path) -> dict[str, str]:
    source_root = project_root / "src" / "skillflow" / "experiment" / "t16"
    return {name: _file_sha256(source_root / name) for name in _LIVE_EXECUTION_SOURCES}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
