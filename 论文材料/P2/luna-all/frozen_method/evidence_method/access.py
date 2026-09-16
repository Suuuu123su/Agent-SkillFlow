"""Policy capability: immutable permitted facts, audited typed queries, no host handle."""
import json
from dataclasses import dataclass
from .bootstrap import canonical, digest

PROFILES = ('full_skillflow', 'baseline_observable')
STRUCTURE = ('use_support', 'object_kind', 'cross_session', 'review_route')
QUERY_KINDS = ('task', 'content', 'tools', 'observations', 'fallback', *STRUCTURE)
STATUSES = ('KNOWN_SUPPORTED', 'KNOWN_UNSUPPORTED', 'UNKNOWN', 'MISSING', 'INCOMPLETE', 'NOT_APPLICABLE')
POLICY_VERSION = 'evidence-clawtrojan-v1/context-dynamic-2'


@dataclass(frozen=True)
class EvidenceResult:
    payload: bytes

    def value(self):
        return json.loads(self.payload)


class EvidenceCache:
    """No content-only verdict cache. Caller cannot request an unscoped cache key."""
    __slots__ = ('_entries',)

    def __init__(self):
        self._entries = {}

    def partition(self, namespace):
        return ScopedCache(self._entries.setdefault(namespace, {}))


class ScopedCache:
    __slots__ = ('_entries',)

    def __init__(self, entries):
        self._entries = entries

    def lookup(self, key):
        return self._entries.get(key)

    def store(self, key, result):
        self._entries[key] = result


class EvidenceContext:
    __slots__ = ('_payload', '_audit', '_cache')

    def __init__(self, permitted_payload, *, cache=None):
        if permitted_payload['profile'] not in PROFILES:
            raise ValueError('unsupported_evidence_profile')
        self._payload = canonical(permitted_payload)
        self._audit = []
        manager = cache if cache is not None else EvidenceCache()
        self._cache = manager.partition((self.profile, self.watermark, POLICY_VERSION))

    @property
    def profile(self):
        return json.loads(self._payload)['profile']

    @property
    def watermark(self):
        return digest(json.loads(self._payload))

    @property
    def binding(self):
        return json.loads(self._payload)['binding']

    def query(self, kind, *, consumer, callsite, use='control', scope=None):
        scope = self.binding.get('scope', '/rule/order') if scope is None else scope
        permitted = kind in QUERY_KINDS and (kind not in STRUCTURE or (use == self.binding['use'] and scope == self.binding.get('scope', '/rule/order')))
        if not permitted:
            # Neither an error nor a blocked query may contain the hidden answer.
            result = {'status': 'MISSING', 'value': None, 'visible_refs': [],
                      'provenance_kind': 'not_exposed_by_context', 'source_category': 'blocked'}
        else:
            value = json.loads(self._payload)
            result = value['answers'][kind]
        key = (self.profile, self.watermark, canonical(self.binding), POLICY_VERSION,
               consumer, kind, use, scope)
        cached = self._cache.lookup(key)
        hit = cached is not None
        if not hit:
            cached = EvidenceResult(canonical(result))
            self._cache.store(key, cached)
        returned = cached.value()
        self._audit.append({'consumer': consumer, 'callsite': callsite, 'query_kind': kind,
            'profile': self.profile, 'use': use, 'scope': scope,
            'source_category': returned['source_category'], 'allowed': permitted,
            'response_status': returned['status'], 'visible_refs': returned['visible_refs'],
            'provenance_kind': returned['provenance_kind'], 'visible_watermark': self.watermark,
            'cache_hit': hit, 'returned_value': returned['value']})
        return returned

    def audit(self):
        return json.loads(canonical(self._audit))

    def export(self):
        return json.loads(self._payload)

    def router_masked(self):
        """Explicit old B diagnostic, never used for system-profile comparison A."""
        data = self.export()
        for key in STRUCTURE:
            data['answers'][key] = unknown('legacy_router_only_mask')
        return EvidenceContext(data)


def known(value, refs, *, source='public_observation', provenance='observed', supported=True):
    return {'status': 'KNOWN_SUPPORTED' if supported else 'KNOWN_UNSUPPORTED',
            'value': value, 'visible_refs': list(refs), 'source_category': source, 'provenance_kind': provenance}


def unknown(provenance='not_observed', *, status='UNKNOWN'):
    return {'status': status, 'value': None, 'visible_refs': [],
            'source_category': 'unavailable', 'provenance_kind': provenance}
