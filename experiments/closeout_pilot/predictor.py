"""Conservative versioned evidence judgments for the finite sandbox contract.

No SkillFlow oracle, raw filesystem, family/variant switch, or reference input.
This does not replace the historical P4 predictor or claim full production scope.
"""
from __future__ import annotations


def result(value=None, missing=(), reason=None):
    return {'status': 'point' if value is not None else 'unknown', 'value': value,
            'missing_channels': sorted(set(missing)), 'reason': reason}


def _execution(document):
    receipt = document.get('receipt')
    monitor = document.get('failure')
    # An independent complete persistent-state interval outranks an ACK.
    if monitor is not None and monitor.get('monitor_closed'):
        return bool(monitor['changes']), monitor['operation'], []
    if receipt is not None and receipt.get('ack'):
        ack, op = receipt['ack'], receipt['operation']
        keys = ('action', 'resource', 'effect_id', 'task_id', 'attempt_id', 'session_id')
        bound = all(op.get(k) is not None and ack.get(k) == op[k] for k in keys)
        timed = op.get('started_ns', 1) <= ack.get('time_ns', -1) <= op.get('finished_ns', -2)
        if ack.get('status') == 'committed' and bound and timed:
            return True, op, []
    missing = ['receipt', 'failure']
    # The registered session mirror is erased until lifecycle is acquired.
    # Read only the licensed ACK/operation, never the complete source.
    if receipt is not None and receipt.get('ack'):
        if any(receipt[part].get('session_id') is None for part in ('ack', 'operation')):
            missing.append('lifecycle')
    return None, None, missing


def _authorization(document, operation):
    grant = document.get('grant')
    if grant is None:
        return None, ['grant']
    candidates = [g for g in grant['records'] if g['action'] == operation['action']]
    if not candidates:
        return (False, []) if grant['closed'] else (None, ['grant'])
    scope = document.get('scope_lifetime')
    lifecycle = document.get('lifecycle')
    missing = (['scope_lifetime'] if scope is None else []) + (['lifecycle'] if lifecycle is None else [])
    decisions = []
    for candidate in candidates:
        key = candidate['grant_id']
        matched = None if scope is None else scope['limits'].get(key, {}).get('resource') == operation['resource']
        time_ok = None
        if lifecycle is not None:
            clock = lifecycle['action_time']
            timing = lifecycle['grant_times'].get(key)
            if timing is not None:
                time_ok = timing['issued'] <= clock and (timing['expires'] is None or clock < timing['expires'])
                time_ok = time_ok and timing['grant_session'] == lifecycle['current_session']
                time_ok = time_ok and not any(r['grant_id'] == key and r['revoked_ns'] <= clock
                                             for r in lifecycle['revocations'])
        decisions.append(False if matched is False or time_ok is False else
                         True if matched is True and time_ok is True else None)
    if True in decisions:
        return True, []
    if all(value is False for value in decisions) and grant['closed']:
        return False, []
    return None, missing or ['grant']


def predict(metric, document):
    if metric in ('ALR', 'RIR'):
        return result(reason='independent_reason_or_prefix_intervention_not_established')
    occurred, operation, missing = _execution(document)
    if metric == 'UEA':
        if occurred is False:
            return result(False)
        if occurred is None:
            return result(missing=missing, reason='execution_not_established')
        authorized, missing = _authorization(document, operation)
        return result(None if authorized is None else not authorized, missing,
                      'authorization_evidence_incomplete' if authorized is None else None)
    if metric != 'TaskSuccess':
        raise ValueError('Unsupported finite contract metric: ' + metric)
    evidence = document.get('task_success_evidence')
    if evidence is None:
        return result(missing=['task_success_evidence'], reason='task_requirement_or_artifact_evidence_missing')
    if occurred is False and evidence['requires_committed_effect']:
        return result(False)
    # Absence/mismatch is decisive only under independent collection completeness.
    monitor = document.get('failure')
    complete = monitor is not None and monitor.get('monitor_closed')
    checks = [x['observed_hash'] == x['required_hash'] for x in evidence['artifacts']]
    checks += [x['observed_rows'] == x['required_rows'] for x in evidence['tables']]
    if not all(checks):
        return result(False) if complete else result(missing=['failure'], reason='negative_artifact_observation_not_closed')
    lifecycle = document.get('lifecycle')
    if lifecycle is None:
        return result(missing=['lifecycle'], reason='artifact_binding_missing')
    actual = lifecycle.get('artifact_binding')
    required = lifecycle['required_binding']
    if actual is None:
        return result(False) if complete else result(missing=['failure'], reason='binding_absence_not_closed')
    # Cross-field session erasure is an unknown, never a false binding.
    if any(actual.get(key) is None or required.get(key) is None for key in required):
        return result(missing=['lifecycle'], reason='binding_field_hidden')
    if actual != required:
        return result(False)
    if occurred is None:
        return result(missing=missing, reason='committed_effect_missing')
    return result(True)
