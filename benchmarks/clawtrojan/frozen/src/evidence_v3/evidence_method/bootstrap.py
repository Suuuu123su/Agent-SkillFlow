"""Standalone reuse of original event store; no legacy launcher or business gate import."""
from .evidence_store import EvidenceStore, canonical, digest, bytehash
class NeedsLive(RuntimeError):
    pass
