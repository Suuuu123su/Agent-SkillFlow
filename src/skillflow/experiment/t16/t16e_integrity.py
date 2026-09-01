"""T16-E 只读加载并冻结 T16-D.2 Model1 基线。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from skillflow.experiment.t16.task_success_canary_models import T16D2CanaryRunSummary
from skillflow.experiment.t16.task_success_live_integrity import sha256_file
from skillflow.experiment.t16.task_success_live_models import T16D2RawTrialRecord
from skillflow.experiment.t16.task_success_live_store import load_t16d2_raw_records

MODEL1_ATTEMPT: Final = Path("runs/t16d2-v31-canary-live-20260830-01/attempt-01")
MODEL1_HASHES: Final = {
    "actual-usage-journal.jsonl": (
        "fff51fbcff81cdd3b9cdbc1ce6b44582a9b1a1e2387759c8202befca13802228"
    ),
    "budget-journal.jsonl": "c61530cb9d29992780700c82de24066d8916ae80677f0b61b584fc8c4c514ea7",
    "effective-config.json": "961590113c2a1d1953af421ed153b52c01bcd749a0b07cd603a3a3e540bd24f0",
    "preflight.json": "2782926b948c73081e4b7024930b37ee8752aba166ba49b7c031be47acab792d",
    "raw-trials.jsonl": "d3af168137c058541a230643bd76f8e8987ff94f1ff4f88bd774320f51f27ab9",
    "run-summary.json": "2ddf8d5fbb30e283bd25deb8ed591332402755e423f786fcb820fcb10e1fccfb",
    "stage-gate-canary.json": "7b65efe0ebedf63622843432e5075c326d9c0f577c397a1daa76b9b1e5237789",
}
CANARY_COUNT: Final = 11
MODEL1_BASELINE_INVALID: Final = "Model1 基线状态或身份不一致"


@dataclass(frozen=True, slots=True)
class T16EModel1Baseline:
    """经过逐文件哈希复核的 Model1 typed evidence。"""

    summary: T16D2CanaryRunSummary
    records: tuple[T16D2RawTrialRecord, ...]


@dataclass(frozen=True, slots=True)
class T16EModel1IntegrityError(RuntimeError):
    """Model1 文件、身份或 11 条结果不再满足冻结基线。"""

    detail: str

    def __str__(self) -> str:
        """返回不包含模型内容的稳定诊断。"""
        return self.detail


def load_t16e_model1_baseline(root: Path) -> T16EModel1Baseline:
    """只读验证 Model1 的 7 个文件并加载严格摘要与 Raw。"""
    attempt = root / MODEL1_ATTEMPT
    for name, expected in MODEL1_HASHES.items():
        path = attempt / name
        if not path.is_file() or sha256_file(path) != expected:
            detail = f"Model1 冻结文件漂移: {name}"
            raise T16EModel1IntegrityError(detail)
    summary = T16D2CanaryRunSummary.model_validate_json(
        (attempt / "run-summary.json").read_text(encoding="utf-8")
    )
    records = load_t16d2_raw_records(attempt / "raw-trials.jsonl")
    if (
        summary.status != "PASSED"
        or summary.observed != CANARY_COUNT
        or len(records) != CANARY_COUNT
        or summary.config_id != "t16d2r-v3.1-canary-gpt-5.6-luna"
    ):
        raise T16EModel1IntegrityError(MODEL1_BASELINE_INVALID)
    return T16EModel1Baseline(summary, records)
