"""按声明计划和 Receipt 证据增量维护独立 Oracle。"""

from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.effects import CapabilityEffect
from skillflow.models.scenario_parts import StepAction
from skillflow.oracle.bindings import bind_attempts, bind_receipts
from skillflow.oracle.effects import oracle_action_semantics
from skillflow.oracle.errors import OracleInvariantError
from skillflow.oracle.expectations import validate_expected_origins
from skillflow.oracle.grants import OracleAuthorizationRequest, OracleGrantResolver
from skillflow.oracle.models import (
    OracleActionPlan,
    OracleEffectTrace,
    OracleInvocationEvidence,
    OracleReceiptEvidence,
    OracleRunPlan,
    OracleSkillPlan,
    OracleTraceRecord,
)
from skillflow.oracle.state import OracleDataState
from skillflow.trace.contracts import ParentRelation, TraceParent


class OracleSidecar:
    """运行决策只写 Observed；该 sidecar 单向接收最小事实投影。"""

    def __init__(self, plan: OracleRunPlan) -> None:
        """在运行前冻结 Scenario、Manifest 和 Scripted 动作。"""
        self._plan = plan
        self._state = OracleDataState(plan.run_id, plan.scenario.assets)
        self._resolver = OracleGrantResolver(plan.scenario.grants)
        self._grant_ids = {grant.grant_id for grant in plan.scenario.grants}
        self._effects: list[OracleEffectTrace] = []
        self._effect_ids: set[str] = set()
        self._recorded_steps: set[str] = set()
        self._skills = self._index_skills(plan.skills)
        self._manifests = self._index_manifests(plan)
        self._steps = {
            step.id: (session.id, step.skill)
            for session in plan.scenario.sessions
            for step in session.steps
            if step.action is StepAction.INVOKE_SKILL
        }

    def record_invocation(self, evidence: OracleInvocationEvidence) -> None:
        """用稳定 ID 绑定一个已完成的 Scripted 调用。"""
        self._validate_invocation(evidence)
        skill_plan = self._skills[evidence.skill_id]
        actions = {action.action_id: action for action in skill_plan.actions}
        if len(actions) != len(skill_plan.actions):
            raise OracleInvariantError(
                "action_plan",
                f"Skill 动作 ID 重复：{evidence.skill_id}",
            )
        attempts = bind_attempts(evidence, actions, self._state)
        action_outputs: list[str] = []
        for action, receipt in bind_receipts(evidence, actions, attempts):
            self._record_action(evidence, action, receipt)
            action_outputs.extend(receipt.output_artifact_ids)
        self._state.record_skill_output(evidence, tuple(action_outputs))
        self._recorded_steps.add(evidence.step_id)

    def record_grant(self, grant: AuthorizationGrant) -> None:
        """只接收 Benchmark 已执行的结构化确认，不读取 Policy。"""
        if grant.grant_id in self._grant_ids:
            raise OracleInvariantError("grant", f"Grant ID 重复：{grant.grant_id}")
        self._resolver = self._resolver.with_grant(grant)
        self._grant_ids.add(grant.grant_id)

    def finalize(self) -> tuple[OracleTraceRecord, ...]:
        """验证完整脚本路径和预注册来源断言后返回只读 Trace。"""
        expected_steps = frozenset(self._steps)
        if self._recorded_steps != expected_steps:
            missing = sorted(expected_steps - self._recorded_steps)
            raise OracleInvariantError(
                "finalize",
                f"Oracle 缺少 invoke step：{','.join(missing)}",
            )
        validate_expected_origins(
            self._plan.scenario,
            self._state,
            tuple(self._effects),
        )
        return (*self._state.records, *self._effects)

    def _record_action(
        self,
        invocation: OracleInvocationEvidence,
        action: OracleActionPlan,
        receipt: OracleReceiptEvidence,
    ) -> None:
        if receipt.call_id != invocation.call_id or receipt.actor_id != invocation.skill_id:
            raise OracleInvariantError(
                "receipt_binding",
                f"Receipt 主体或 call_id 不一致：{receipt.receipt_id}",
            )
        if receipt.tool is not action.arguments.kind:
            raise OracleInvariantError(
                "receipt_binding",
                f"Receipt Tool 与动作不一致：{receipt.action_id}",
            )
        semantics = oracle_action_semantics(action.arguments)
        output_ids = self._state.record_outputs(action, receipt)
        self._state.record_receipt(invocation.skill_id, receipt, output_ids)
        authorization = self._resolver.resolve(
            OracleAuthorizationRequest(
                actor_id=invocation.skill_id,
                effect=semantics.effect,
                manifest_permissions=self._manifests[invocation.skill_id],
                task_id=self._plan.scenario.task.id,
                session_id=invocation.session_id,
                call_id=invocation.call_id,
                effect_time=receipt.timestamp,
            )
        )
        if receipt.effect_id in self._effect_ids:
            raise OracleInvariantError(
                "stable_id",
                f"Oracle Effect ID 重复：{receipt.effect_id}",
            )
        self._effect_ids.add(receipt.effect_id)
        parent_ids = (receipt.argument_artifact_id, *output_ids)
        self._effects.append(
            OracleEffectTrace(
                run_id=self._plan.run_id,
                effect_id=receipt.effect_id,
                action_id=receipt.action_id,
                actor_id=receipt.actor_id,
                task_id=self._plan.scenario.task.id,
                session_id=invocation.session_id,
                call_id=receipt.call_id,
                timestamp=receipt.timestamp,
                effect=semantics.effect,
                gt_data=self._state.effect_data(receipt, output_ids),
                gt_auth=authorization.gt_auth,
                gt_effect=True,
                manifest_declared=authorization.manifest_declared,
                matched_grant_ids=authorization.matched_grant_ids,
                receipt_id=receipt.receipt_id,
                parents=tuple(
                    TraceParent(parent_id=item, relation=ParentRelation.INVOKE)
                    for item in parent_ids
                ),
            )
        )

    def _validate_invocation(self, evidence: OracleInvocationEvidence) -> None:
        if evidence.step_id in self._recorded_steps:
            raise OracleInvariantError(
                "invocation_binding",
                f"Step 重复执行：{evidence.step_id}",
            )
        try:
            expected_session, expected_skill = self._steps[evidence.step_id]
        except KeyError as error:
            raise OracleInvariantError(
                "invocation_binding",
                f"未声明 invoke step：{evidence.step_id}",
            ) from error
        if expected_session != evidence.session_id or expected_skill != evidence.skill_id:
            raise OracleInvariantError(
                "invocation_binding",
                f"Step/Session/Skill 绑定不一致：{evidence.step_id}",
            )
        if evidence.skill_id not in self._skills:
            raise OracleInvariantError(
                "invocation_binding",
                f"Skill 缺少 Oracle 动作计划：{evidence.skill_id}",
            )

    @staticmethod
    def _index_skills(skills: tuple[OracleSkillPlan, ...]) -> dict[str, OracleSkillPlan]:
        indexed = {skill.skill_id: skill for skill in skills}
        if len(indexed) != len(skills):
            raise OracleInvariantError("run_plan", "Oracle Skill plan ID 重复")
        return indexed

    @staticmethod
    def _index_manifests(plan: OracleRunPlan) -> dict[str, tuple[CapabilityEffect, ...]]:
        indexed: dict[str, tuple[CapabilityEffect, ...]] = {}
        for binding in plan.manifests:
            if binding.skill_id in indexed:
                raise OracleInvariantError(
                    "run_plan",
                    f"Oracle Manifest 绑定重复：{binding.skill_id}",
                )
            if binding.manifest.id != binding.skill_id:
                raise OracleInvariantError(
                    "run_plan",
                    f"Manifest ID 与 Skill 不一致：{binding.skill_id}",
                )
            requested = binding.manifest.requested_permissions
            indexed[binding.skill_id] = requested or binding.manifest.declared_permissions
        expected = {skill.id for skill in plan.scenario.skills}
        if set(indexed) != expected:
            missing = sorted(expected - set(indexed))
            raise OracleInvariantError(
                "run_plan",
                f"Skill 缺少 Manifest 真值：{','.join(missing)}",
            )
        return indexed
