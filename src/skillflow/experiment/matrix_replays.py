"""Matrix 变体的反事实重放与标准 ReplayResult 落盘。"""

import hashlib

from skillflow.analysis.report_io import write_replay_risk_report
from skillflow.benchmark.replay import ReplayRunner, ReplayRunRequest
from skillflow.benchmark.replay_models import ReplayPairManifest
from skillflow.experiment.inputs import slug
from skillflow.experiment.io import write_json_model
from skillflow.experiment.layout import ExperimentLayout
from skillflow.experiment.matrix_support import ExecutedVariant
from skillflow.models.reports import ReplayRiskReport


def run_matrix_replays(
    item: ExecutedVariant,
    layout: ExperimentLayout,
    experiment_id: str,
    redacted: bool,
    runner: ReplayRunner,
) -> tuple[ReplayRiskReport, ...]:
    """执行一个变体的全部反事实，并只保留规范化 pair/report 产物。"""
    if not item.scenario.counterfactuals:
        return ()
    namespace = hashlib.sha256(item.variant.variant.encode()).hexdigest()[:8]
    staging = layout.root / "blobs" / "r" / namespace
    batch = runner.run_configured(
        ReplayRunRequest(
            scenario_path=item.scenario_path,
            scenario=item.scenario,
            replay_root=staging,
            seed=f"{item.result.run_id}:{item.variant.seed}:replay",
            id_namespace=slug(item.variant.variant),
            experiment_id=experiment_id,
            source_run_id=item.result.run_id,
            scenario_ref=item.variant.scenario,
            redacted=redacted,
        )
    )
    for pair in batch.pairs:
        destination = layout.root / "replays" / pair.report.replay_id
        destination.mkdir(parents=False, exist_ok=False)
        manifest = ReplayPairManifest.model_validate_json(
            pair.manifest_path.read_text(encoding="utf-8")
        )
        write_json_model(destination / "pair-manifest.json", manifest)
        write_replay_risk_report(destination / "replay-report.json", pair.report)
    return tuple(pair.report for pair in batch.pairs)
