"""Pure licensed-input acquisition rules; no raw files, labels, or Full inputs."""
from __future__ import annotations

from .common import CHANNELS

PRIORITY = {
    'UEA': ['receipt', 'grant', 'scope_lifetime', 'lifecycle', 'failure'],
    'TaskSuccess': ['task_success_evidence', 'lifecycle', 'receipt', 'failure'],
    'ALR': ['provenance', 'decision_reason', 'counterfactual', 'receipt'],
    'RIR': ['lifecycle', 'provenance', 'counterfactual', 'receipt'],
}


def complete_order(order):
    return list(dict.fromkeys(list(order) + list(CHANNELS)))


def choose(metric, policy_name, prediction, acquired, order, quotes, remaining):
    """Public quote may affect affordable choice; hidden payload length may not."""
    candidates = [name for name in order if name not in acquired
                  and quotes[name] <= remaining]
    if policy_name == 'dependency_guided':
        needed = set(prediction['missing_channels'])
        preferred = [name for name in candidates if name in needed]
        if preferred:
            return preferred[0]
    return candidates[0] if candidates else None
