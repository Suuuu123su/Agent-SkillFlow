import json
from pathlib import Path


def test_openclaw_driver_has_an_explicit_esm_package_boundary() -> None:
    package_path = Path("integrations/openclaw/package.json")

    package = json.loads(package_path.read_text(encoding="utf-8"))

    assert package == {"name": "skillflow-openclaw-pilot", "private": True, "type": "module"}


def test_openclaw_driver_explicitly_allows_only_the_needed_conversation_hook() -> None:
    config = Path("integrations/openclaw/gateway-config.ts").read_text(encoding="utf-8")

    assert "hooks: { allowConversationAccess: true }" in config
    assert "skills: params.plan.skills.map((item) => item.skill_id)" in config
    assert "allowBundled: []" in config


def test_observer_manifest_declares_the_planned_skill_config_contract() -> None:
    manifest_path = Path("integrations/openclaw/skillflow-observer/openclaw.plugin.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = manifest["configSchema"]

    assert "skills" in schema["required"]
    assert schema["properties"]["skills"]["items"]["required"] == [
        "skillId",
        "relativePath",
    ]
