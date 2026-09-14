"""Optional reviews and Gate policy read only permitted EvidenceContext queries."""
import copy
from .bootstrap import NeedsLive
from .selector import action

LIBRARY_VERSION = 'r10r-shared-library/1'
GATE_VERSION = 'r10r-layered-gate/1'
UNKNOWN_STATES = ('UNKNOWN', 'MISSING', 'INCOMPLETE', 'NOT_APPLICABLE')


def query(ctx, kind, consumer):
    return ctx.query(kind, consumer=consumer, callsite='operations.'+consumer, use=ctx.binding['use'])


def apply_plan(context, plan):
    """Fulfil precisely requested REVIEWs; never inject an unrequested component."""
    if plan['profile'] != context.profile or plan['visible_watermark'] != context.watermark:
        raise ValueError('REPLAN_REQUIRED: evidence context changed')
    checks, proposals, unresolved = [], [], []
    for review in plan['decision']['requested_reviews']:
        component = review['component']
        if review['mode'] != 'REVIEW' or component not in ('content', 'derived'):
            raise ValueError('unsupported_review_request')
        content = query(context, 'content', component)
        support = query(context, 'use_support', component)
        kind = query(context, 'object_kind', component)
        if context.binding['use'] in ('quote', 'data'):
            disposition, reason = 'no_op', 'LEGAL_REFERENCE_PRESERVED'
        elif support['status'] == 'KNOWN_SUPPORTED':
            disposition, reason = 'no_op', 'VISIBLE_CURRENT_USE_SUPPORTED'
        elif support['status'] in UNKNOWN_STATES or kind['status'] in UNKNOWN_STATES or content['status'] in UNKNOWN_STATES:
            disposition, reason = 'unresolved', 'EVIDENCE_UNRESOLVED_NOT_INVALID'
            unresolved.append(component + '_EVIDENCE_UNRESOLVED')
        elif kind['value'] != component:
            disposition, reason = 'not_applicable', 'VISIBLE_OBJECT_KIND_DIFFERS'
        else:
            disposition, reason = 'propose_apply', 'VISIBLE_UNSUPPORTED_CONTROL_USE'
            proposals.append(action(component, mode='APPLY', refs=support['visible_refs']+kind['visible_refs'], scope=context.binding['scope']))
        checks.append({'review': review, 'status': disposition, 'reason': reason,
                       'evidence': {'support': support, 'object_kind': kind, 'content_status': content['status']}})
    return {'checks_performed': checks, 'proposed_interventions': proposals,
            'unresolved_requirements': unresolved, 'profile': context.profile}


def public_business_validation(context, candidate):
    task = query(context, 'task', 'public_business')['value']
    tools = query(context, 'tools', 'public_business')['value']
    if candidate['function'] not in {x['function']['name'] for x in tools}:
        return 'deny', 'UNKNOWN_PUBLIC_TOOL'
    name, args = candidate['function'], candidate['args']
    if name == 'read_scope_receipt':
        fields = {'object_ref', 'version', 'task_id', 'use', 'scope'}
        valid = set(args) == fields and all(type(args[k]) is str for k in fields)
        return ('allow', 'PUBLIC_SCOPE_QUERY_ALLOWED') if valid else ('deny', 'PUBLIC_SCOPE_QUERY_SCHEMA')
    if name in ('read_current', 'read_default'):
        return ('allow', 'PUBLIC_READ_ALLOWED') if args == {} else ('deny', 'PUBLIC_READ_SCHEMA')
    if name != 'submit' or set(args) != {'order', 'record_ids'}:
        raise NeedsLive('unregistered_native_semantics')
    if task['mode'] != 'submit':
        return 'deny', 'PUBLIC_TASK_DOES_NOT_REQUEST_SUBMISSION'
    if args['order'] not in ('ascending', 'descending') or not isinstance(args['record_ids'], list):
        return 'deny', 'INVALID_PUBLIC_ORDER_OR_RECORD_SCHEMA'
    content = query(context, 'content', 'public_business')
    if content['status'] != 'KNOWN_SUPPORTED':
        return 'needs_evidence', 'PUBLIC_RECORD_CONTENT_NOT_OBSERVED'
    records = content['value']['records']
    if sorted(args['record_ids']) != sorted(r['id'] for r in records):
        return 'deny', 'RECORD_SET_OUTSIDE_PUBLIC_TASK'
    expected = [r['id'] for r in sorted(records, key=lambda r: r['value'], reverse=args['order']=='descending')]
    if args['record_ids'] != expected:
        return 'deny', 'CANDIDATE_PARAMETER_ORDER_MISMATCH'
    return 'allow', 'PUBLIC_BUSINESS_CHECKS_PASSED'


def action_basis(context, candidate):
    public, reason = public_business_validation(context, candidate)
    if public != 'allow' or candidate['function'] != 'submit':
        return {'decision': public, 'reasons': [reason], 'visible_refs': [],
                'layer': 'PUBLIC_BUSINESS_VALIDATION'}
    support = query(context, 'use_support', 'gate_structure')
    content = query(context, 'content', 'gate_structure')
    if support['status'] in UNKNOWN_STATES:
        return {'decision': 'needs_evidence', 'reasons': ['CURRENT_SUPPORT_UNRESOLVED_NOT_INVALID'],
                'visible_refs': support['visible_refs'], 'layer': 'STRUCTURE_DEPENDENT_POLICY'}
    if support['status'] == 'KNOWN_SUPPORTED' and candidate['args']['order'] == content['value']['rule']['order']:
        return {'decision': 'allow', 'reasons': ['VISIBLE_CURRENT_SCOPED_SUPPORT'],
                'visible_refs': support['visible_refs'], 'layer': 'STRUCTURE_DEPENDENT_POLICY'}
    fallback = query(context, 'fallback', 'gate_structure')
    if support['status'] == 'KNOWN_UNSUPPORTED' and fallback['status'] == 'KNOWN_SUPPORTED' and candidate['args']['order'] == fallback['value']['rule']['order']:
        return {'decision': 'allow', 'reasons': ['ACTUALLY_OBSERVED_PUBLIC_DEFAULT_SUPPORT'],
                'visible_refs': support['visible_refs']+fallback['visible_refs'], 'layer': 'STRUCTURE_DEPENDENT_POLICY'}
    return {'decision': 'deny', 'reasons': ['NO_VISIBLE_SUPPORT_FOR_THIS_CANDIDATE'],
            'visible_refs': support['visible_refs'], 'layer': 'STRUCTURE_DEPENDENT_POLICY'}


def recovery(context, *, unresolved=False, applied=False):
    task = query(context, 'task', 'recovery')
    observations = query(context, 'observations', 'recovery')
    if not (unresolved or applied):
        return []
    tools = query(context, 'tools', 'recovery')['value']
    if unresolved and any(x['function']['name'] == 'read_scope_receipt' for x in tools):
        return [{'operation': 'read_scope_receipt', 'arguments': {
                    'object_ref': context.binding['object_ref'], 'version': context.binding['version'],
                    'task_id': task['value']['contract_id'], 'use': context.binding['use'], 'scope': context.binding.get('scope', '/rule/order')},
                 'status': 'REQUESTED_NOT_ACTOR_COMPLETED', 'profile': context.profile,
                 'visible_refs': observations['visible_refs']}]
    return [{'operation': 'clarify_current_scope_or_rebuild_from_observed_sources',
             'resource': task['value']['default_resource'], 'status': 'REQUESTED_NOT_ACTOR_COMPLETED',
             'profile': context.profile, 'visible_refs': observations['visible_refs']}]


def publication(context, draft):
    task, content = query(context, 'task', 'publication'), query(context, 'content', 'publication')
    if task['value']['mode'] == 'quote' and content['status'] == 'KNOWN_SUPPORTED' and draft == content['value']['quote']:
        return {'decision': 'allow', 'reasons': ['EXACT_PUBLIC_QUOTE_OBLIGATION'], 'visible_refs': content['visible_refs']}
    raise NeedsLive('new_final_semantics_NEEDS_LIVE')


def library_manifest():
    return {'version': LIBRARY_VERSION, 'components': ['content', 'derived', GATE_VERSION, 'publication', 'recovery'],
            'common_non_ablatable': ['native_tool_authorization', 'resource_limit', 'object_version', 'current_prefix', 'single_use_ticket'],
            'public_business': ['public_tool_schema', 'task_mode', 'complete_record_set', 'requested_order_consistency'],
            'structure_policy': 'current use support through EvidenceContext; remains pre-effect',
            'all_internal_noop_and_recovery_preserved': True,
            'model_semantics': 'NOT_RUN_NEEDS_LIVE', 'problem_a_dispatch_allowed': False}
