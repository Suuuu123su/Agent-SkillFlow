"""Fixed public quotes and exact, padded canonical UTF-8 transport accounting."""
from __future__ import annotations

import copy
import json

from .common import CHANNELS, canonical, sha
from .dependencies import apply_bundle, project, restoration_bundle


def padded_packet(bundle, quote):
    value = {'bundle': bundle, 'padding': ''}
    raw = canonical(value)
    if len(raw) > quote:
        raise ValueError(f'Predeclared packet quote too small: {len(raw)} > {quote}')
    value['padding'] = ' ' * (quote - len(raw))
    raw = canonical(value)
    assert len(raw) == quote
    return raw


_INITIAL_CACHE = {}
_PACKET_CACHE = {}


class Broker:
    """Cooperative input separation; not an OS security boundary."""

    def __init__(self, document, initially_visible, quotes):
        self._document = document  # Immutable source; all outputs are copies.
        self._key = sha(canonical(document))
        self.quotes = dict(quotes)
        cache_key = (self._key, tuple(sorted(initially_visible)), tuple(sorted(quotes.items())))
        if cache_key in _INITIAL_CACHE:
            self.visible, self.events, self.total = copy.deepcopy(_INITIAL_CACHE[cache_key])
            self.acquired = set(initially_visible)
            self.initial_bytes = self.total
            return
        self.acquired = set(initially_visible)
        self.visible = project(document, set())
        # Empty public contract and quotes are charged once, including control metadata.
        header = canonical({'document': self.visible, 'quotes': self.quotes,
                            'transport': 'padded-canonical-v1'})
        self.total = len(header)
        self.events = [{'kind': 'public_header', 'channel': None, 'bytes': len(header),
                        'sha256': sha(header), 'total': self.total}]
        self.acquired = set()
        for channel in CHANNELS:
            if channel in initially_visible:
                self._accept(channel, None, 'initial')
        self.initial_bytes = self.total
        _INITIAL_CACHE[cache_key] = copy.deepcopy((self.visible, self.events, self.total))

    def _accept(self, channel, budget, kind):
        if channel in self.acquired:
            raise ValueError('Cached evidence must not be retransmitted silently')
        quote = self.quotes[channel]
        if budget is not None and self.total + quote > budget:
            raise ValueError('Over-budget request refused before payload access')
        packet_key = (self._key, tuple(sorted(self.acquired)), channel, quote)
        if packet_key not in _PACKET_CACHE:
            bundle = restoration_bundle(self._document, self.acquired, [channel])
            raw = padded_packet(bundle, quote)
            _PACKET_CACHE[packet_key] = (raw, sha(raw))
        raw, packet_sha = _PACKET_CACHE[packet_key]
        # Decode precisely the transmitted representation; no hidden-document merge.
        wire_bundle = json.loads(raw)['bundle']
        self.visible = apply_bundle(self.visible, wire_bundle)
        self.acquired.add(channel)
        self.total += len(raw)
        self.events.append({'kind': kind, 'channel': channel, 'bytes': len(raw),
                            'sha256': packet_sha, 'total': self.total})
        assert self.visible == project(self._document, self.acquired)

    def acquire(self, channel, budget):
        self._accept(channel, budget, 'acquire')


def calibration_quotes(documents):
    """Development-only worst subset packets, padded to a fixed 1 KiB grid.

    Quote values are global for every query and are frozen before heldout access.
    Conservative 2x development maxima plus 1 KiB is a predeclared overflow guard.
    """
    maximum = {name: 0 for name in CHANNELS}
    for doc in documents:
        for channel in CHANNELS:
            others = [name for name in CHANNELS if name != channel]
            # Dependency closure packets are largest at empty and fully acquired;
            # all masks are verified later against these fixed quotes by M0 checks.
            for acquired in (set(), set(others)):
                bundle = restoration_bundle(doc, acquired, [channel])
                maximum[channel] = max(maximum[channel], len(canonical({'bundle': bundle, 'padding': ''})))
    return {name: ((2 * size + 1023) // 1024 + 1) * 1024 for name, size in maximum.items()}


def clear_transport_cache():
    """CPU memoization only: cached packet bytes are still charged on every wire replay."""
    _INITIAL_CACHE.clear()
    _PACKET_CACHE.clear()
