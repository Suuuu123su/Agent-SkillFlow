"""Raw-record to licensed evidence conversion. No reference labels or decisions."""
from __future__ import annotations

import base64
import copy
import json
import re

CONTRACT = 'controlled-persistent-effect-v1'


def adapt(record):
    schedule = record['permission_schedule']
    supervisor = record['supervisor']
    attempt = record['attempt']
    requirements = record['task_requirements']
    state = supervisor['state_after']
    artifacts = []
    for wanted in requirements['artifacts']:
        actual = state.get(wanted['path'])
        artifacts.append({'path': wanted['path'], 'required_hash': wanted['sha256'],
                          'observed_hash': actual['sha256'] if actual else None})
    tables = []
    for wanted in requirements['database_checks']:
        match = re.fullmatch(r'SELECT (\w+(?:,\w+)*) FROM (\w+) ORDER BY (\w+)', wanted['query'])
        if match is None:
            raise ValueError('Adapter only supports the preregistered all-column SELECT contract')
        actual = state.get(wanted['path'], {}).get('sqlite_tables', {}).get(match[2])
        tables.append({'database': wanted['path'], 'query': wanted['query'],
                       'required_rows': wanted['expected_rows'], 'observed_rows': actual})
    binding_record = state.get(requirements['binding_path'])
    binding = json.loads(base64.b64decode(binding_record['content_base64'])) if binding_record else None
    grants = schedule['grants']
    operation = {'action': attempt['action'], 'resource': attempt['resource'], 'task_id': attempt['task_id'], 'attempt_id': record['attempt_id'], 'effect_id': supervisor['effect_id'], 'session_id': attempt['session_id'], 'started_ns': attempt['started_ns'], 'finished_ns': attempt['finished_ns']}
    document = {
        'id': record['execution_unit_id'], 'contract_version': CONTRACT,
        'public': {'protocol': CONTRACT, 'source_class': 'controlled_program'},
        'receipt': {'operation': operation, 'ack': ({k:v for k,v in record['collector']['receipt'].items() if k != 'artifact_hashes'} if record['collector']['receipt'] else None)},
        'grant': {'closed': schedule['complete'],
                  'records': [{'grant_id': grant['grant_id'], 'action': grant['action']} for grant in grants]},
        'scope_lifetime': {'limits': {grant['grant_id']: {'resource': grant['resource']}
                                      for grant in grants}},
        'lifecycle': {'action_time': attempt['started_ns'], 'current_session': attempt['session_id'],
                      'grant_times': {grant['grant_id']: {'issued': grant['issued_ns'],
                          'expires': grant['expires_ns'], 'grant_session': grant['session_id']} for grant in grants},
                      'revocations': copy.deepcopy(schedule['revocations']),
                      'artifact_binding': binding, 'required_binding': requirements['binding']},
        'task_success_evidence': {'artifacts': artifacts, 'tables': tables,
                                  'requires_committed_effect': requirements['requires_committed_effect']},
        'failure': {'monitor_closed': supervisor['complete'], 'operation': operation,
                    'changes': [{'path': change['path'], 'effect_id': supervisor['effect_id']} for change in supervisor['side_effect_records']],
                    'return_code': supervisor['process_returncode'], 'timed_out': supervisor['timed_out']},
        'provenance': {'reference_scope': 'data_lineage_only', 'reason_contrast_available': False},
        'decision_reason': {'recorded_agent_reason': None},
        'counterfactual': {'identity': None, 'neutral': None, 'confirmed_prefix': None},
    }
    return document


def query_records(record):
    metrics = ['UEA', 'TaskSuccess']
    if record['construct'] in ('ALR', 'RIR'):
        metrics.append(record['construct'])
    return [{'query_id': record['execution_unit_id'] + ':' + metric,
             'unit': record['execution_unit_id'], 'family_id': record['family_id'],
             'metric': metric, 'source_id': record['source_id'], 'split': record['split'],
             'fault_event': bool(record['collector']['acknowledgment_lost'])}
            for metric in metrics]
