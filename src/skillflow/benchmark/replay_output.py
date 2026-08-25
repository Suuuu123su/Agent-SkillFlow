"""T10 Replay 报告与证据清单的不可覆盖写入。"""

import json
from pathlib import Path

from skillflow.analysis.errors import ReplayManifestWriteError
from skillflow.analysis.report_io import write_replay_risk_report
from skillflow.benchmark.replay_models import ReplayPairManifest
from skillflow.models.reports import ReplayRiskReport


def write_replay_outputs(
    output_root: Path,
    report: ReplayRiskReport,
    manifest: ReplayPairManifest,
) -> tuple[Path, Path]:
    """独占创建风险报告和不含正文、路径的配对清单。"""
    report_path = output_root / "replay-report.json"
    manifest_path = output_root / "pair-manifest.json"
    write_replay_risk_report(report_path, report)
    content = json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    try:
        with manifest_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.write("\n")
    except OSError as error:
        raise ReplayManifestWriteError(manifest_path, str(error)) from error
    return report_path, manifest_path
