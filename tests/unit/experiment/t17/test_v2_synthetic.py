"""两个额外的本地合成技能通过完整执行、复算和技能比较入口。"""

import hashlib
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.catalog_models import CatalogCondition, SkillBundle, SkillCatalog
from skillflow.experiment.t17.v2.claim_setup import claim_specs
from skillflow.experiment.t17.v2.config_models import V2Configuration
from skillflow.experiment.t17.v2.configuration import build_configuration, write_configuration
from skillflow.experiment.t17.v2.dataset_io import export_dataset
from skillflow.experiment.t17.v2.loading import load_stage
from skillflow.experiment.t17.v2.matrix import build_matrix
from skillflow.experiment.t17.v2.skill_comparison import skill_vectors_and_pairs
from skillflow.experiment.t17.v2.stage import StageSetup, run_stage
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document


def _synthetic_config(root: Path, destination: Path) -> V2Configuration:
    base, bundles = build_configuration(root, destination)
    source = next(
        c for c in base.catalog.conditions if c.configuration.variant == "c1-context-grid-p11"
    )
    entry = next(e for e in base.catalog.variants if e.skill_variant_id == source.skill_variant_id)
    original = bundles[entry.source_path]
    producer = next(key for key, script in original.scripts.items() if not script.actions)
    scenario = validate_yaml_document(root / entry.scenario_path, Scenario)
    entries, conditions, new_bundles, claims = [], [], {}, {}
    # 故意令标签与危险内容相反，证明标签不是数值判定器。
    for name, role, text in (
        ("local-synthetic-alpha", "attack", b'{"send":"no "}'),
        ("local-synthetic-beta", "neutral", b'{"send":"yes"}'),
    ):
        scripts = {**original.scripts, producer: replace(original.scripts[producer], output=text)}
        bundle = SkillBundle(bundle_id=name, scripts=scripts, decisions=original.decisions)
        path = destination.relative_to(root).as_posix() + "/skills/" + name + ".json"
        new_bundles[path] = bundle
        changed = entry.model_dump()
        changed.update(
            skill_variant_id=name,
            source_path=path,
            attack_family="not-a-result-label",
            variant_role=role,
            split="held-out",
            pair_id="local-synthetic-pair",
            neutral_pair_skill_id="local-synthetic-beta" if role == "attack" else None,
            skill_content_sha256=hashlib.sha256(
                (bundle.model_dump_json(indent=2, by_alias=True) + "\n").encode()
            ).hexdigest(),
        )
        entries.append(changed)
        conditions.append(
            CatalogCondition(
                skill_variant_id=name,
                configuration=source.configuration.model_copy(update={"variant": name}),
            )
        )
        claims[name] = claim_specs(scenario, bundle)
    config = V2Configuration.model_validate(
        {
            **base.model_dump(),
            "catalog": SkillCatalog.model_validate(
                {
                    "catalog_id": "two-additional-local-skills",
                    "variants": entries,
                    "conditions": conditions,
                }
            ),
            "tasks": tuple(t for t in base.tasks if t.scenario_path == entry.scenario_path),
            "hiaa_designs": (),
            "session_pairs": (),
            "claim_bindings": claims,
        }
    )
    write_configuration(root, destination, config, new_bundles)
    return config


def test_two_new_held_out_skills_compare_through_real_facts_and_fresh_process(
    t17_cli_root: Path,
) -> None:
    root = Path.cwd()
    config = _synthetic_config(root, t17_cli_root / "synthetic-inputs")
    matrix = build_matrix(root, config, T17LiveStage.CANARY)
    assert matrix.scheduled_core_trials == 2
    assert matrix.scheduled_replay_pairs == 2
    result = run_stage(
        StageSetup(root, t17_cli_root / "synthetic-run", config, matrix, "scripted", None)
    )
    assert result.gate.passed, result.gate.failures
    loaded = load_stage(root, t17_cli_root / "synthetic-run")
    vectors, pairs = skill_vectors_and_pairs(loaded.group(), "two-local-skills")
    assert len(vectors) == 2
    assert len(pairs) == 1
    assert pairs[0].left.metrics["verified_target_effect"].value == 0
    assert pairs[0].right.metrics["verified_target_effect"].value == 1
    assert pairs[0].left.identity.raw_manifest_sha256 == (loaded.raw_manifest.sha256,)
    assert (
        pairs[0].left.identity.skill_content_sha256 != pairs[0].right.identity.skill_content_sha256
    )
    dataset = t17_cli_root / "synthetic-dataset"
    export_dataset(root, dataset, (loaded,))
    comparison = t17_cli_root / "synthetic-comparison"
    environment = {**os.environ, "PYTHONHASHSEED": "2", "PYTHONDONTWRITEBYTECODE": "1"}
    checked = subprocess.run(
        [
            sys.executable,
            "-m",
            "skillflow.cli",
            "compare-skills",
            "--dataset",
            str(dataset),
            "--output",
            str(comparison),
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert (comparison / "skill-comparison.json").is_file()
