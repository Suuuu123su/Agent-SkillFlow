"""Host-generated event state. No scenario labels, scores or expected actions."""
import copy
import json
from dataclasses import dataclass

from .bootstrap import EvidenceStore, bytehash, canonical, digest


class BindingError(ValueError):
    pass


@dataclass(frozen=True)
class OnlineEvidenceSnapshot:
    # Immutable canonical bytes, not a frozen wrapper around a mutable dictionary.
    payload: bytes
    sha256: str

    def value(self):
        if digest(json.loads(self.payload)) != self.sha256:
            raise BindingError('snapshot_integrity')
        return json.loads(self.payload)


class HostState:
    def __init__(self, run_id='controlled-run'):
        self.store = EvidenceStore(run_id)
        self.run_id = run_id
        self.session = 'session-1'
        self.objects = {}
        self.heads = {}
        self.task = None

    def event(self, kind, **data):
        eid = self.store.record('r10_' + kind, {'session': self.session, **data})
        # Optional trusted public issuer publishes invalidations synchronously.
        # No listener means precisely the existing event semantics.
        for notify in tuple(getattr(self, '_public_receipt_listeners', ())):
            notify(copy.deepcopy(self.store.events[-1]))
        return eid

    def register_task(self, task):
        if self.task is not None:
            raise BindingError('task_already_registered')
        self.task = copy.deepcopy(task)
        return self.event('task', task=self.task, issuer='trusted_user')

    def register(self, key, value, *, origin='external_tool', parents=(), read_event=None):
        if key in self.objects:
            raise BindingError('object_version_already_exists')
        if parents and not read_event:
            raise BindingError('derivation_requires_actual_read')
        text = canonical(value).decode()
        record = {'object_ref': key, 'version': bytehash(text), 'text': text,
                  'origin': origin, 'parents': list(parents), 'read_event': read_event}
        eid = self.event('produce', **record)
        self.objects[key] = {**record, 'producer_event_id': eid}
        return key

    def read_object(self, key):
        obj = self.objects[key]
        eid = self.event('read', object_ref=key, version=obj['version'])
        return json.loads(obj['text']), eid

    def derive_copy(self, key, parent):
        value, read_event = self.read_object(parent)
        # Exact dependency is justified by this actual deterministic copy.
        return self.register(key, value, origin='derived_copy',
                             parents=({'object_ref': parent, 'version': self.objects[parent]['version'],
                                       'scope': '/rule/order', 'precision': 'exact_copy'},),
                             read_event=read_event)

    def grant(self, key, use, scope='/rule/order'):
        return self.event('grant', object_ref=key, version=self.objects[key]['version'],
                          use=use, scope=scope, issuer='trusted_user', task=self.task['contract_id'])

    def revoke(self, grant):
        issued = self.store.require_event(grant, 'r10_grant')
        return self.event('revoke', grant_event=issued['event_id'], issuer='trusted_user')

    def memory_write(self, key, obj):
        if obj not in self.objects:
            raise BindingError('unknown_memory_object')
        eid = self.event('memory_write', key=key, object_ref=obj, version=self.objects[obj]['version'])
        self.heads[key] = {'object_ref': obj, 'version': self.objects[obj]['version'], 'event_id': eid}
        return eid

    def next_session(self):
        self.session = 'session-2'
        self.event('session_start')

    def snapshot(self, obj, *, timing, use, candidate=None, prefix_size=None):
        if obj not in self.objects:
            raise BindingError('object_not_registered')
        n = len(self.store.events) if prefix_size is None else prefix_size
        if n < 1 or n > len(self.store.events):
            raise BindingError('invalid_prefix')
        events = copy.deepcopy(self.store.events[:n])
        if self.store.events[:n] != events:
            raise BindingError('prefix_changed')
        value = {'run_id': self.run_id, 'session_id': self.session, 'boundary': timing,
                 'boundary_index': n, 'events': events, 'objects': copy.deepcopy(self.objects),
                 'heads': copy.deepcopy(self.heads), 'task': copy.deepcopy(self.task),
                 'current_object': obj, 'current_version': self.objects[obj]['version'],
                 'use': use, 'candidate': copy.deepcopy(candidate)}
        snap = OnlineEvidenceSnapshot(canonical(value), digest(value))
        validate(snap)
        return snap

    def clone(self):
        return copy.deepcopy(self)


def validate(snapshot):
    v = snapshot.value()
    previous = None
    by_id = {}
    for i, e in enumerate(v['events']):
        body = {k: val for k, val in e.items() if k != 'sha256'}
        if (e['run_id'] != v['run_id'] or e['previous_sha256'] != previous
                or digest(body) != e['sha256'] or e['event_id'] != f'event-{i+1:06d}'):
            raise BindingError('event_identity_or_prefix_integrity')
        previous = e['sha256']
        by_id[e['event_id']] = e
    if v['boundary_index'] != len(by_id):
        raise BindingError('future_or_incomplete_prefix')
    for key, obj in v['objects'].items():
        e = by_id.get(obj['producer_event_id'])
        if (e is None or e['kind'] != 'r10_produce' or e['data']['object_ref'] != key
                or any(e['data'][k] != val for k, val in obj.items() if k != 'producer_event_id')
                or bytehash(obj['text']) != obj['version']):
            raise BindingError('object_version_producer_binding')
        for parent in obj['parents']:
            p = v['objects'].get(parent['object_ref'])
            r = by_id.get(obj['read_event'])
            if (not p or p['version'] != parent['version'] or not r or r['kind'] != 'r10_read'
                    or r['data']['object_ref'] != parent['object_ref']
                    or r['data']['version'] != parent['version']
                    or r['event_id'] >= e['event_id'] or obj['text'] != p['text']):
                raise BindingError('derivation_without_actual_copy')
    for key, head in v['heads'].items():
        event = by_id.get(head['event_id'])
        if (not event or event['kind'] != 'r10_memory_write'
                or any(event['data'][k] != val for k, val in head.items() if k != 'event_id')
                or event['data']['key'] != key):
            raise BindingError('memory_head_binding')
        later = [e for e in v['events'] if e['kind'] == 'r10_memory_write' and e['data']['key'] == key]
        if later[-1]['event_id'] != head['event_id']:
            raise BindingError('stale_memory_head')
    tasks = [e for e in v['events'] if e['kind'] == 'r10_task']
    if len(tasks) != 1 or tasks[0]['data']['task'] != v['task'] or tasks[0]['data']['issuer'] != 'trusted_user':
        raise BindingError('task_binding')
    if v['current_version'] != v['objects'][v['current_object']]['version']:
        raise BindingError('wrong_current_version')
    latest_session = v['events'][-1]['data']['session']
    if latest_session != v['session_id']:
        raise BindingError('session_binding')
    return v


def use_support(v, key, use, scope='/rule/order', seen=()):
    """Policy fact, not semantic support, poisoning truth or inferred causality."""
    if key in seen:
        raise BindingError('dependency_cycle')
    obj = v['objects'][key]
    ids = [obj['producer_event_id']]
    if obj['parents']:
        results = [use_support(v, p['object_ref'], use, p['scope'], (*seen, key)) for p in obj['parents']]
        return all(r[0] for r in results), ids + [i for r in results for i in r[1]]
    revoked = {e['data']['grant_event']: e['event_id'] for e in v['events'] if e['kind'] == 'r10_revoke'}
    grants = [e for e in v['events'] if e['kind'] == 'r10_grant'
              and e['data']['object_ref'] == key and e['data']['version'] == obj['version']
              and e['data']['use'] == use and e['data']['scope'] == scope
              and e['data']['task'] == v['task']['contract_id'] and e['data']['issuer'] == 'trusted_user']
    ids += [e['event_id'] for e in grants]
    ids += [revoked[e['event_id']] for e in grants if e['event_id'] in revoked]
    return any(e['event_id'] not in revoked for e in grants), ids


def mechanism_features(snapshot):
    v = validate(snapshot)
    key = v['current_object']
    obj = v['objects'][key]
    supported, ids = use_support(v, key, v['use'])
    derived = bool(obj['parents'])
    mem = [h for h in v['heads'].values() if h['object_ref'] == key]
    features = {
        'current_use_support': supported, 'actual_derived_dependency': derived,
        'current_memory_binding': bool(mem),
        'cross_session': any(e['event_id'] == obj['producer_event_id'] and e['data']['session'] != v['session_id'] for e in v['events']),
        'relevant_use_invalid': not supported,
        'public_alternative': v['task']['default_resource'],
    }
    task_ids = [e['event_id'] for e in v['events'] if e['kind'] == 'r10_task']
    return {k: {'value': val, 'availability': 'available',
                'producer_event_ids': task_ids if k == 'public_alternative' else ids,
                'observed_at_boundary': v['boundary_index'], 'authority_kind': 'host_observed_registry'}
            for k, val in features.items()}
