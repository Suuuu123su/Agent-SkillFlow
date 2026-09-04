"""从预注册撤销因素机械建立会话对照表，不读运行结果。"""

from skillflow.experiment.t17.minimal.contracts import NormalTaskContract
from skillflow.experiment.t17.v2.catalog_models import SkillCatalog
from skillflow.experiment.t17.v2.paired_models import SessionPairDesign
from skillflow.models.matrix_axes import SkillStateCondition


def session_pairs(
    catalog: SkillCatalog, tasks: tuple[NormalTaskContract, ...]
) -> tuple[SessionPairDesign, ...]:
    """只为明确声明撤销因素、且存在同一配对中性条件的配置生成设计。"""
    by_path = {t.scenario_path: t for t in tasks}
    result: dict[str, SessionPairDesign] = {}
    for target in catalog.conditions:
        variant = target.configuration
        if variant.skill_state is not SkillStateCondition.REVOKED or variant.pair_id is None:
            continue
        controls = tuple(
            c
            for c in catalog.conditions
            if c.configuration.pair_id == variant.pair_id
            and not c.configuration.target_skill_present
        )
        identities = {c.skill_variant_id for c in controls}
        if len(identities) != 1:
            raise ValueError("v2_session_pair_control_missing")
        design = SessionPairDesign(
            pair_id=variant.pair_id,
            target_skill_variant_id=target.skill_variant_id,
            control_skill_variant_id=next(iter(identities)),
            selectors=by_path[variant.scenario.root].risk_selectors,
        )
        if design.pair_id in result and result[design.pair_id] != design:
            raise ValueError("v2_session_pair_ambiguous")
        result[design.pair_id] = design
    return tuple(result[key] for key in sorted(result))
