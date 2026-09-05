"""首次正式冻结前机械生成全部必需和固定探索补证。"""

from skillflow.experiment.t19.campaign import CampaignPlan
from skillflow.experiment.t19.matrix import formal


def formal_plan() -> CampaignPlan:
    """144必需候选加24预选候选；任何效果未知时就已确定。"""
    trials = formal()
    aliases: dict[str, tuple[str, ...]] = {}
    for trial in trials:
        if trial.mechanism == "A1":
            aliases[trial.trial_id] = ("authorization-claim",)
        elif trial.mechanism == "M2":
            aliases[trial.trial_id] = ("m2-memory-1", "m2-memory-3")
        elif (
            trial.mechanism in {"C1", "C2"}
            and trial.role == "attack"
            and trial.bridge
            and trial.repeat == 1
        ):
            aliases[trial.trial_id] = (
                ("context-input",) if trial.mechanism == "C1" else ("tool-return",)
            )
    return CampaignPlan(domain="live_reference", fixed=("T",), trials=trials, audit_aliases=aliases)
