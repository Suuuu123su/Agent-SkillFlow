"""新版技能目录必须先验证能力匹配，再生成任何运行计划。"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from skillflow.experiment.t17.v2.catalog_models import SkillCatalog, SkillVariant
from skillflow.experiment.t17.v2.frozen import digest_files, verify_files


def entry(identifier: str, role: str = "neutral") -> dict[str, object]:
    return {
        "skill_variant_id": identifier,
        "skill_family": "synthetic-context",
        "attack_family": "annotation-only",
        "variant_role": role,
        "skill_version": "1.0",
        "source_path": "skills/" + identifier + ".json",
        "scenario_path": "scenarios/paired.yaml",
        "scenario_sha256": "a" * 64,
        "skill_content_sha256": ("b" if role == "attack" else "c") * 64,
        "manifest_paths": ["scenarios/manifests/context.yaml"],
        "manifest_sha256": "d" * 64,
        "capability_fingerprint": "e" * 64,
        "tool_registry_fingerprint": "f" * 64,
        "input_schema_fingerprint": "1" * 64,
        "output_schema_fingerprint": "2" * 64,
        "task_contract_id": "normal-task:synthetic-v2",
        "neutral_pair_skill_id": "neutral" if role == "attack" else None,
        "pair_id": "synthetic-pair",
        "risk_effect_selector": [],
        "harness_factor": ["shared_context"],
        "scope_requirements": [],
        "lifetime_requirements": ["task"],
        "split": "held-out",
    }


def test_catalog_allows_different_content_with_matched_capability() -> None:
    catalog = SkillCatalog.model_validate(
        {"catalog_id": "synthetic", "variants": [entry("attack", "attack"), entry("neutral")]}
    )
    assert len(catalog.variants) == 2
    assert catalog.variants[0].split == "held-out"
    assert catalog.variants[0].skill_content_sha256 != catalog.variants[1].skill_content_sha256


@pytest.mark.parametrize(
    "field",
    [
        "manifest_sha256",
        "capability_fingerprint",
        "tool_registry_fingerprint",
        "input_schema_fingerprint",
        "output_schema_fingerprint",
        "task_contract_id",
        "skill_version",
        "pair_id",
        "split",
        "scope_requirements",
        "lifetime_requirements",
    ],
)
def test_catalog_rejects_unmatched_pair(field: str) -> None:
    attack, neutral = entry("attack", "attack"), entry("neutral")
    if field == "scope_requirements":
        neutral[field] = [
            {
                "action": "network.send",
                "source_pattern": "context:/x",
                "sink_pattern": "mock://other",
            }
        ]
    elif field == "lifetime_requirements":
        neutral[field] = ["session"]
    elif field == "split":
        neutral[field] = "development"
    else:
        neutral[field] = "9" * 64
    with pytest.raises(ValidationError):
        SkillCatalog.model_validate({"catalog_id": "bad", "variants": [attack, neutral]})


@pytest.mark.parametrize("path", ["../secret.json", "C:/tmp/key.json", "/etc/passwd", "a\\b"])
def test_catalog_rejects_host_paths(path: str) -> None:
    value = entry("neutral")
    value["source_path"] = path
    with pytest.raises(ValidationError, match="relative_path"):
        SkillVariant.model_validate(value)


def test_catalog_rejects_duplicate_and_missing_pair() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        SkillCatalog.model_validate({"catalog_id": "x", "variants": [entry("n"), entry("n")]})
    with pytest.raises(ValidationError, match="pair_missing"):
        SkillCatalog.model_validate({"catalog_id": "x", "variants": [entry("a", "attack")]})


def test_frozen_hashes_are_read_only_and_detect_changed_bytes(tmp_path: Path) -> None:
    # 使用测试源码作输入，测试本身不制造或改写任何历史文件。
    root = Path(__file__).resolve().parents[4]
    relative = Path(__file__).resolve().relative_to(root).as_posix()
    hashes = digest_files(root, (relative,))
    verify_files(root, hashes)
    tampered = {relative: hashes[relative].model_copy(update={"sha256": "0" * 64})}
    with pytest.raises(ValueError, match="frozen_file_drift"):
        verify_files(root, tampered)
    with pytest.raises(ValueError, match="relative_path"):
        digest_files(root, ("../outside",))
