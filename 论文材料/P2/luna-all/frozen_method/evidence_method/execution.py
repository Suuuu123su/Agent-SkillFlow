"""Trusted orchestration: immutable REVIEW, then separately frozen APPLY, no labels."""
import copy
from .bootstrap import digest
from .selector import select, bind
from .operations import apply_plan, recovery


def execute_content(services, context, config, *, reviewer=apply_plan):
    decision = select(context, config)
    frozen = bind(context, decision, services)
    return execute_plan(services, context, frozen, reviewer=reviewer)


def execute_plan(services, context, frozen, *, diagnostic_label=None, reviewer=apply_plan):
    # Diagnostic label is deliberately not a semantic input.
    services.validate_plan(context, frozen)
    review_result = reviewer(context, frozen)
    services.audit.append({'kind': 'requested_reviews_completed', 'parent_plan_hash': digest(frozen),
                           'profile': context.profile, 'result': review_result})
    actual_plan = frozen
    if frozen['decision']['requested_reviews']:
        decision = copy.deepcopy(frozen['decision'])
        decision['requested_reviews'] = []
        decision['proposed_interventions'] = review_result['proposed_interventions']
        decision['unresolved_requirements'] = review_result['unresolved_requirements']
        decision['reason_codes'] = ['RESULT_OF_EXPLICIT_REQUESTED_REVIEW']
        actual_plan = bind(context, decision, services, parent=frozen)
    operations = actual_plan['decision']['proposed_interventions']
    requests = recovery(context, unresolved=bool(actual_plan['decision']['unresolved_requirements']), applied=bool(operations))
    raw, delivered, changes = services.apply_operations(context, actual_plan, operations)
    result = {'initial_frozen_plan': frozen, 'applied_frozen_plan': actual_plan,
              'checks_performed': review_result['checks_performed'], 'operations_applied': operations,
              'raw_text': raw, 'delivered_text': delivered, 'state_changes': changes,
              'recovery_requests': requests, 'unresolved_requirements': actual_plan['decision']['unresolved_requirements'],
              'profile': context.profile, 'evidence_context': context.export(), 'access_audit': context.audit(),
              'future_actor_outcome': None, 'status': 'NEEDS_EVIDENCE' if actual_plan['decision']['unresolved_requirements'] else 'LOCAL_EXECUTED'}
    # Signature reflects operations/effects, not selection names or optional review counts.
    result['effective_signature'] = {'delivered_text': delivered, 'state_changes': changes,
                                      'recovery_requests': requests}
    result['effective_signature_hash'] = digest(result['effective_signature'])
    return result
