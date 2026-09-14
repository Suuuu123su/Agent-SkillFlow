"""Selection uses only EvidenceContext; policy and evidence profile are independent."""
from .access import EvidenceContext
from .bootstrap import digest
from .config import DefenseConfig, STRATEGIES

VERSION = 'evidence-dynamic-selector/2'
MASKED = ('use_support', 'object_kind', 'cross_session')


def view(context, *, masked=False):
    if not isinstance(context, EvidenceContext):
        raise TypeError('Policy requires EvidenceContext; raw host/snapshot forbidden')
    return context.router_masked() if masked else context


def _read(ctx, kind):
    return ctx.query(kind, consumer='selector', callsite='selector.choose', use=ctx.binding['use'])


def action(component, *, mode='REVIEW', refs=(), scope='/rule/order'):
    return {'component': component, 'mode': mode,
            'action': 'review_current_use' if mode == 'REVIEW' else 'restrict_control',
            'scope': [scope], 'visible_refs': list(refs)}


def choose(context, config=None):
    config = config or DefenseConfig(evidence_profile=context.profile)
    if config.evidence_profile != context.profile:
        raise ValueError('selection_context_profile_mismatch')
    visible = view(context, masked=config.legacy_diagnostic == 'legacy_router_masked')
    task = _read(visible, 'task')
    _read(visible, 'observations')
    reviews, applies, unresolved, reasons = [], [], [], []
    if config.selection_policy in ('fixed_config', 'all_applicable'):
        components = config.fixed.components if config.fixed is not None else STRATEGIES['K3']
        reviews = [action(c, scope=context.binding['scope']) for c in components]
        reasons = ['EXPLICIT_FIXED_CONFIG' if config.fixed else 'ALL_APPLICABLE_REVIEWS']
    elif context.binding['use'] in ('quote', 'data'):
        reasons = ['RETAIN_LEGAL_REFERENCE']
    else:
        support, kind = _read(visible, 'use_support'), _read(visible, 'object_kind')
        _read(visible, 'cross_session')
        if support['status'] == 'KNOWN_SUPPORTED':
            reasons = ['CURRENT_USE_SUPPORTED']
        elif support['status'] == 'KNOWN_UNSUPPORTED' and kind['status'] == 'KNOWN_SUPPORTED':
            applies = [action(kind['value'], mode='APPLY', refs=support['visible_refs'] + kind['visible_refs'], scope=context.binding['scope'])]
            reasons = ['VISIBLE_UNSUPPORTED_CONTROL_USE']
        else:
            route = _read(visible, 'review_route')
            components = tuple(route['value']['components']) if route['status'] == 'KNOWN_SUPPORTED' else STRATEGIES['K3']
            reviews = [action(c, scope=context.binding['scope']) for c in components]
            unresolved = ['CURRENT_USE_OR_OBJECT_KIND_UNRESOLVED']
            reasons = ['SEMANTIC_ROUTE_IS_FALLIBLE_CHECK_SELECTION_NOT_AUTHORITY']
    result = {'schema': 'r10r-selection/1', 'version': VERSION, 'selection_policy': config.selection_policy,
              'profile': context.profile, 'visible_watermark': context.watermark,
              'requested_reviews': reviews, 'proposed_interventions': applies,
              'unresolved_requirements': unresolved, 'recovery_intent': [], 'reason_codes': reasons,
              'fixed_status': 'FixedPreRegistered('+config.fixed.strategy_id+')' if config.fixed else None,
              'legacy_diagnostic': config.legacy_diagnostic,
              'feature_access': visible.audit()}
    if reviews or applies:
        result['recovery_intent'] = [{'resource': task['value']['default_resource'], 'status': 'QUERY_IF_NEEDED_NO_BACKGROUND_READ'}]
    return result


def bind(context, decision, binding_service, *, parent=None):
    # Trusted boundary does mechanical registration only; no optional policy inference.
    return binding_service.freeze(context, decision, parent=parent)


def select(context, config=None):
    return choose(context, config)
