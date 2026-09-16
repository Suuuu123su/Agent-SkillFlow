"""Append-only content/event bindings for the native semantic adaptation."""
import copy
import hashlib
import json
import os
from pathlib import Path
from .errors import DefenseRuntimeError


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def bytehash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def span(text, quote):
    value = quote.model_dump() if hasattr(quote, 'model_dump') else quote
    start = -1
    for _ in range(value['occurrence'] + 1):
        start = text.find(value['text'], start + 1)
        if start < 0:
            raise DefenseRuntimeError('quote_not_in_bound_source')
    return {'start': start, 'end': start + len(value['text']), 'exact_text': value['text'],
            'index_unit': 'unicode_code_point', 'source_utf8_sha256': bytehash(text)}


class EvidenceStore:
    def __init__(self, run_id, directory=None):
        self.run_id = run_id
        self.directory = Path(directory) if directory else None
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=False)
        self.events = []
        self._event_hashes = []
        self.sources = {}

    def record(self, kind, data):
        value = {'schema_version': 'native-semantic-evidence/1', 'run_id': self.run_id,
                 'event_id': f'event-{len(self.events)+1:06d}', 'kind': kind,
                 'previous_sha256': self.events[-1]['sha256'] if self.events else None,
                 'data': copy.deepcopy(data)}
        value['sha256'] = digest(value)
        if self.directory:
            with (self.directory/'events.jsonl').open('a', encoding='utf-8') as f:
                f.write(canonical(value).decode('utf-8')+'\n');f.flush();os.fsync(f.fileno())
        self.events.append(value)
        self._event_hashes.append(value['sha256'])
        return value['event_id']

    def require_event(self, identifier, kind):
        try:
            index = int(identifier.removeprefix('event-')) - 1
            event = self.events[index]
            body = {k: v for k, v in event.items() if k != 'sha256'}
            if (index < 0 or event['event_id'] != identifier or event['kind'] != kind
                or digest(body) != self._event_hashes[index] or event['sha256'] != self._event_hashes[index]):
                raise ValueError('event_integrity')
        except (ValueError, IndexError, KeyError, AttributeError) as error:
            raise DefenseRuntimeError('required_event_missing_or_corrupt') from error
        return copy.deepcopy(event)

    def add_source(self, raw, delivered, *, call, decision_id, origin):
        identifier = f'source-{len(self.sources)+1:04d}'
        value = {'source_id': identifier, 'run_id': self.run_id, 'version': 1,
                 'raw_text': raw, 'delivered_text': delivered,
                 'raw_sha256': bytehash(raw), 'delivered_sha256': bytehash(delivered),
                 'call': copy.deepcopy(call), 'post_tool_decision_id': decision_id,
                 'origin': origin, 'control_authority': 'not_a_grant',
                 'derivation_precision': 'observed_whole_return_parent_not_model_internal_causality'}
        value['event_id'] = self.record('artifact_observe_and_deliver', value)
        self.sources[identifier] = value
        return identifier

    def source_views(self):
        for source in self.sources.values():
            event = self.require_event(source['event_id'], 'artifact_observe_and_deliver')
            if event['data'] != {k:v for k,v in source.items() if k != 'event_id'}:
                raise DefenseRuntimeError('source_event_binding')
            if not source['origin'].startswith('LOCAL_'):
                decision = self.require_event(source['post_tool_decision_id'], 'post_tool_decision')['data']
                if (decision['raw_sha256'] != source['raw_sha256'] or decision['delivered_sha256'] != source['delivered_sha256']
                    or decision['actual_call_sha256'] != digest(source['call'])):
                    raise DefenseRuntimeError('post_tool_decision_binding')
            if bytehash(source['raw_text']) != source['raw_sha256'] or bytehash(source['delivered_text']) != source['delivered_sha256']:
                raise DefenseRuntimeError('source_content_integrity')
        return copy.deepcopy(list(self.sources.values()))

    def verify_ref(self, ref, user, *, raw=False):
        ref = ref.model_dump() if hasattr(ref, 'model_dump') else ref
        sid = ref['source_id']
        if sid == 'user':
            text = user
        else:
            self.source_views()
            if sid not in self.sources:
                raise DefenseRuntimeError('unobserved_source_reference')
            text = self.sources[sid]['raw_text' if raw else 'delivered_text']
        return {'source_id': sid, 'view': 'raw' if raw and sid != 'user' else 'delivered', **span(text, ref['quote'])}
