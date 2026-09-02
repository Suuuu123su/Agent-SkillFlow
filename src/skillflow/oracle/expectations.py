"""用预注册断言校验机械 Oracle 路径，不用断言填充真值。"""

from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import EffectSelector
from skillflow.oracle.errors import OracleInvariantError
from skillflow.oracle.models import OracleEffectTrace
from skillflow.oracle.state import OracleDataState


def validate_expected_origins(
    scenario: Scenario,
    state: OracleDataState,
    effects: tuple[OracleEffectTrace, ...],
    *,
    require_effect_receipts: bool = True,
) -> None:
    """要求机械传播结果覆盖 Scenario 预注册的来源断言。"""
    artifacts_by_alias = {alias: record for record in state.records for alias in record.aliases}
    selectors = {selector.alias: selector for selector in scenario.effect_selectors}
    for expectation in scenario.oracle.expected_origins:
        target = expectation.target.root
        if target.startswith("artifact:"):
            try:
                actual = set(artifacts_by_alias[target].gt_data)
            except KeyError as error:
                raise OracleInvariantError(
                    "expected_origins",
                    f"Oracle Artifact alias 未绑定：{target}",
                ) from error
        else:
            alias = expectation.target.alias
            selector = selectors[alias]
            matching = tuple(
                effect for effect in effects if _effect_matches_selector(effect, selector)
            )
            if not matching:
                if not require_effect_receipts:
                    continue
                raise OracleInvariantError(
                    "expected_origins",
                    f"Effect selector 没有实际 Receipt：{alias}",
                )
            actual = {origin for effect in matching for origin in effect.gt_data}
        expected = {
            state.asset_origin(origin.identifier)
            if origin.root.startswith("asset:")
            else origin.identifier
            for origin in expectation.origins
        }
        if not expected <= actual:
            missing = sorted(expected - actual)
            raise OracleInvariantError(
                "expected_origins",
                f"机械路径缺少预注册来源：{target}：{','.join(missing)}",
            )


def _effect_matches_selector(
    effect: OracleEffectTrace,
    selector: EffectSelector,
) -> bool:
    actual_source = effect.effect.source
    expected_source = selector.source_pattern
    source_matches = (actual_source is None and expected_source is None) or (
        actual_source is not None
        and expected_source is not None
        and expected_source.matches_exact(actual_source)
    )
    return (
        source_matches
        and selector.action is effect.effect.action
        and selector.sink_pattern.matches_exact(effect.effect.sink)
    )
