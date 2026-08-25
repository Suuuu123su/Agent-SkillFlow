import hashlib
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from skillflow.benchmark.manifests import load_manifests
from skillflow.benchmark.scripted_backend import FixtureScript
from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.instrumentation.tool_types import HttpSendArgs, ShellExecArgs
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_research import PairFactor
from skillflow.validation import validate_yaml_document

SCENARIO_ROOT = Path("scenarios")
CORE_IDS = {"B0", "B1", "N0", "C1", "C2", "M1", "M2", "A1", "A2", "S1", "L1", "G0"}
ATTACK_IDS = {"B1", "C1", "C2", "M1", "M2", "A1", "S1", "L1"}


def _scenario_files() -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                *SCENARIO_ROOT.joinpath("benign").glob("*.yaml"),
                *SCENARIO_ROOT.joinpath("attacks").glob("*.yaml"),
            )
        )
    )


def test_twelve_core_scenarios_and_controls_close_all_references() -> None:
    scripts, _ = t12_fixture_registry()
    records = tuple((path, validate_yaml_document(path, Scenario)) for path in _scenario_files())
    scenarios = {scenario.id: (path, scenario) for path, scenario in records}

    assert set(scenarios) >= CORE_IDS
    assert len(scenarios) == 16
    for path, scenario in records:
        assert scenario.pairing is not None
        assert scenario.canary is not None
        assert scenario.success_assertions
        assert scenario.expected_metrics
        assert all(skill.implementation.root in scripts for skill in scenario.skills)
        assert all(asset.uri.root.startswith("fixture://") for asset in scenario.assets)
        load_manifests(path, scenario)

    for scenario_id, (_, scenario) in scenarios.items():
        assert scenario.pairing is not None
        paired_id = scenario.pairing.paired_scenario_id
        assert paired_id in scenarios
        paired = scenarios[paired_id][1]
        assert paired.pairing is not None
        assert paired.pairing.pair_id == scenario.pairing.pair_id
        assert paired.pairing.paired_scenario_id == scenario_id


def test_every_attack_points_to_a_benign_capability_control() -> None:
    scenarios = {
        scenario.id: path
        for path in _scenario_files()
        for scenario in (validate_yaml_document(path, Scenario),)
    }

    for attack_id in ATTACK_IDS:
        attack = validate_yaml_document(scenarios[attack_id], Scenario)
        assert attack.pairing is not None
        control_path = scenarios[attack.pairing.paired_scenario_id]
        assert control_path.parent.name == "benign"


def test_every_pair_preserves_capabilities_except_its_declared_factor() -> None:
    scripts, _ = t12_fixture_registry()
    records = {
        scenario.id: scenario
        for path in _scenario_files()
        for scenario in (validate_yaml_document(path, Scenario),)
    }
    checked: set[str] = set()

    for scenario in records.values():
        assert scenario.pairing is not None
        if scenario.pairing.pair_id in checked:
            continue
        paired = records[scenario.pairing.paired_scenario_id]
        assert paired.pairing is not None
        checked.add(scenario.pairing.pair_id)

        assert scenario.pairing.factor is paired.pairing.factor
        assert _skill_profiles(scenario, scripts) == _skill_profiles(paired, scripts)
        assert _invocation_shapes(scenario) == _invocation_shapes(paired)
        assert _asset_shapes(scenario) == _asset_shapes(paired)
        if scenario.pairing.factor not in {
            PairFactor.GRANT,
            PairFactor.AUTHORIZATION_SOURCE,
        }:
            assert _grant_shapes(scenario) == _grant_shapes(paired)


def test_fixture_catalog_covers_every_asset_canary_and_skill_implementation() -> None:
    payload = yaml.safe_load(Path("scenarios/fixtures/catalog.yaml").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    catalog_assets = {
        (entry["uri"], variant["content"]): variant["sha256"]
        for entry in payload["assets"]
        for variant in entry["variants"]
    }
    scripts, _ = t12_fixture_registry()

    assert set(payload["skill_implementations"]) == set(scripts)
    for path in _scenario_files():
        scenario = validate_yaml_document(path, Scenario)
        assert scenario.canary is not None
        asset = next(item for item in scenario.assets if item.id == scenario.canary.asset_id)
        content = asset.marker if asset.marker is not None else asset.id
        digest = hashlib.sha256(content.encode()).hexdigest()
        assert catalog_assets[(asset.uri.root, content)] == digest
        assert scenario.canary.sha256 == digest


def test_t12_registry_contains_no_shell_or_real_network_action() -> None:
    scripts, _ = t12_fixture_registry()

    assert all(key.startswith("fixture://") for key in scripts)
    for script in scripts.values():
        for action in script.actions:
            assert not isinstance(action.arguments, ShellExecArgs)
            if isinstance(action.arguments, HttpSendArgs):
                assert action.arguments.sink.root.startswith("mock://")


def test_all_t12_scenarios_and_manifests_match_static_json_schemas() -> None:
    scenario_validator = Draft202012Validator(
        json.loads(Path("schemas/scenario.schema.json").read_text(encoding="utf-8"))
    )
    manifest_validator = Draft202012Validator(
        json.loads(Path("schemas/skill-manifest.schema.json").read_text(encoding="utf-8"))
    )

    for path in _scenario_files():
        scenario = validate_yaml_document(path, Scenario)
        scenario_validator.validate(json.loads(scenario.model_dump_json()))
    for path in sorted(Path("scenarios/manifests").glob("*.yaml")):
        manifest_validator.validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _skill_profiles(
    scenario: Scenario,
    scripts: dict[str, FixtureScript],
) -> tuple[object, ...]:
    profiles = []
    for skill in scenario.skills:
        script = scripts[skill.implementation.root]
        profiles.append(
            (
                skill.id,
                skill.manifest.root,
                script.output_mime_type,
                len(script.output),
                tuple(type(action.arguments).__name__ for action in script.actions),
            )
        )
    return tuple(sorted(profiles))


def _invocation_shapes(scenario: Scenario) -> tuple[object, ...]:
    return tuple(
        sorted(
            (
                step.skill,
                len(step.inputs),
                len(step.outputs),
                len(step.tool_outputs),
            )
            for session in scenario.sessions
            for step in session.steps
            if step.skill is not None and step.action.value == "invoke_skill"
        )
    )


def _asset_shapes(scenario: Scenario) -> tuple[object, ...]:
    return tuple(
        sorted(
            (
                asset.id,
                asset.uri.root,
                asset.trust.value,
                asset.sensitivity,
                len(asset.marker if asset.marker is not None else asset.id),
            )
            for asset in scenario.assets
        )
    )


def _grant_shapes(scenario: Scenario) -> tuple[object, ...]:
    grants = scenario.grants + tuple(
        step.grant
        for session in scenario.sessions
        for step in session.steps
        if step.grant is not None
    )
    return tuple(sorted(grant.model_dump_json() for grant in grants))
