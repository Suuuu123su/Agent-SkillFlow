"""任务对齐、预先规划工具依赖与成对因果归因的本地机制适配。"""

from skillflow.defense.router import HIGH_SEVERITY
from skillflow.defense.task_plan import CausalAssessment, GateRequest, GateResult, matching_nodes


class TaskAlignmentGate:
    """Task Shield 的确定性任务合同适配，不使用额外模型判断。"""

    def evaluate(self, request: GateRequest) -> GateResult:
        """工具必须服务于任务的合法效果或必需数据依赖。"""
        evidence = request.signals.evidence_ids
        if not matching_nodes(request):
            return GateResult(action="deny", reason="NOT_IN_TASK_CONTRACT", evidence_ids=evidence)
        if not request.authorized:
            return GateResult(action="confirm", reason="TASK_REQUIRES_GRANT", evidence_ids=evidence)
        return GateResult(action="allow", reason="TASK_ALIGNED", evidence_ids=evidence)


class ToolDependencyGuard:
    """IPIGuard 的可信预先规划适配；不让外部数据扩写执行图。"""

    def evaluate(self, request: GateRequest) -> GateResult:
        """前置节点完成后才可执行精确节点，已用节点不能重复扩大行为。"""
        available = tuple(
            node
            for node in matching_nodes(request)
            if node.node_id not in request.completed_node_ids
        )
        if any(set(node.predecessor_ids) <= request.completed_node_ids for node in available):
            return GateResult(
                action="allow",
                reason="PLANNED_DEPENDENCY_READY",
                evidence_ids=request.signals.evidence_ids,
            )
        return GateResult(
            action="deny",
            reason="UNPLANNED_OR_UNREADY_TOOL",
            evidence_ids=request.signals.evidence_ids,
        )


class CausalAttributionGate:
    """AttriGuard 的检查点适配；没有实现随机模型的模糊生存阈值。"""

    @staticmethod
    def requires_replay(request: GateRequest) -> bool:
        """仅对实际准备放行的高风险候选来源路径申请成对重放。"""
        return (
            request.base_executed
            and request.signals.target_effect_requested
            and request.signals.candidate_influence
            and request.signals.sink_severity >= HIGH_SEVERITY
        )

    def evaluate(self, request: GateRequest, assessment: CausalAssessment) -> GateResult:
        """被中和移除的动作拒绝；存活动作仍需通过原有授权约束。"""
        if not self.requires_replay(request):
            return GateResult(
                action="allow",
                reason="CAUSAL_CHECK_NOT_NEEDED",
                evidence_ids=request.signals.evidence_ids,
            )
        if assessment.status != "measured":
            return GateResult(
                action="confirm",
                reason="CAUSAL_EVIDENCE_UNAVAILABLE",
                evidence_ids=request.signals.evidence_ids,
                abstain=True,
            )
        if assessment.ci == 1:
            return GateResult(
                action="deny",
                reason="CAUSAL_CONTROL_CONFIRMED",
                evidence_ids=assessment.evidence_ids,
            )
        if assessment.ci == -1 or not request.authorized:
            return GateResult(
                action="confirm",
                reason="SURVIVAL_DOES_NOT_GRANT_AUTHORITY",
                evidence_ids=assessment.evidence_ids,
            )
        return GateResult(
            action="allow",
            reason="TARGET_SURVIVES_NEUTRALIZATION",
            evidence_ids=assessment.evidence_ids,
        )
