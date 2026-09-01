"""T16-C 条件编译器共享的严格元数据。"""

from dataclasses import dataclass

from skillflow.experiment.t16.live_design_models import BaseDesignFields
from skillflow.experiment.t16.matrix import TrialSpec
from skillflow.experiment.t16.preregistration_models import T16Condition


@dataclass(frozen=True, slots=True)
class UnknownLiveConditionError(ValueError):
    """Matrix Trial 引用了预注册之外的条件。"""

    condition_id: str

    def __str__(self) -> str:
        """返回不含模型输入的稳定诊断。"""
        return f"未注册 condition: {self.condition_id}"


def base_design_fields(condition: T16Condition, spec: TrialSpec) -> BaseDesignFields:
    """返回每个条件构造器必须原样保留的预注册元数据。"""
    return {
        "matrix_trial_id": spec.trial_id,
        "scenario": spec.scenario,
        "condition_id": spec.condition_id,
        "semantic_instance_id": spec.semantic_instance_id,
        "pair_id": spec.pair_id,
        "repeat_index": spec.repeat_index,
        "task_prompt": spec.task_prompt,
        "pair_role": condition.pair_role,
        "independent_factor": condition.independent_factor,
        "hiaa_cell": condition.hiaa_cell,
        "harm_selector": condition.harm_selector,
        "observation_sessions": condition.observation_sessions,
        "intervention": condition.intervention,
    }
