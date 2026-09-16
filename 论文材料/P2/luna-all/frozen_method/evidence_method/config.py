"""Orthogonal selection policy and evidence profile. No implicit Best Fixed."""
from dataclasses import dataclass, asdict
from .access import PROFILES

STRATEGIES = {'K0': (), 'K1': ('content',), 'K2': ('derived',), 'K3': ('content', 'derived')}


class FixedNotCalibrated(ValueError):
    pass


@dataclass(frozen=True)
class FixedPolicySpec:
    strategy_id: str
    components: tuple[str, ...]
    version: str = 'fixed-policy/1'
    provenance: str = 'pre_registered'

    def __post_init__(self):
        if self.strategy_id not in STRATEGIES or self.components != STRATEGIES[self.strategy_id]:
            raise ValueError('fixed_policy_components_do_not_match_explicit_versioned_spec')
        if self.version != 'fixed-policy/1' or self.provenance != 'pre_registered':
            raise FixedNotCalibrated('FIXED_NOT_CALIBRATED')

    @classmethod
    def registered(cls, strategy):
        return cls(strategy, STRATEGIES[strategy])


@dataclass(frozen=True)
class DefenseConfig:
    selection_policy: str = 'dynamic'
    evidence_profile: str = 'full_skillflow'
    fixed: FixedPolicySpec | None = None
    legacy_diagnostic: str | None = None

    def __post_init__(self):
        if self.evidence_profile not in PROFILES or self.selection_policy not in ('dynamic', 'fixed_config', 'all_applicable'):
            raise ValueError('unsupported_policy_profile_combination')
        if (self.selection_policy == 'fixed_config') != (self.fixed is not None):
            raise ValueError('explicit_fixed_spec_required_only_for_fixed_config')
        if self.legacy_diagnostic not in (None, 'legacy_router_masked'):
            raise ValueError('unknown_legacy_diagnostic')
        if self.legacy_diagnostic and (self.evidence_profile != 'full_skillflow' or self.selection_policy != 'dynamic'):
            raise ValueError('legacy_router_mask_is_only_old_B_diagnostic')

    def value(self):
        return asdict(self)


def legacy_config(method, strategy=None):
    if method == 'Fixed-DevBest':
        raise FixedNotCalibrated('FIXED_NOT_CALIBRATED: no complete development selection record')
    if strategy is not None:
        return DefenseConfig('fixed_config', 'full_skillflow', FixedPolicySpec.registered(strategy))
    if method == 'All-SameLibrary':
        return DefenseConfig('all_applicable')
    if method == 'StructuralMasked':
        return DefenseConfig(legacy_diagnostic='legacy_router_masked')
    if method == 'FixedPreRegistered(K3)':
        return DefenseConfig('fixed_config', fixed=FixedPolicySpec.registered('K3'))
    if method == 'Evidence-Dynamic':
        return DefenseConfig()
    raise ValueError('unsupported_legacy_method')


def validate_future_a_pair(first, second):
    a, b = first.value(), second.value()
    a.pop('evidence_profile')
    b.pop('evidence_profile')
    if a != b or first.legacy_diagnostic or second.legacy_diagnostic:
        raise ValueError('Problem A requires same algorithm/policy and no router-only diagnostic')
    return {'design_comparable': True, 'dispatch_allowed': False}
