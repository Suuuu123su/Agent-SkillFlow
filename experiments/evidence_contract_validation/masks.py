"""Predeclared channel loss mechanisms, never exposed as labels to policies."""
import random

from .common import CHANNELS, SEEDS


def conditions(unit_id, fault_event):
    result = []
    for channel in CHANNELS:
        result.append({'condition': 'channel_' + channel, 'mechanism': 'whole_channel',
                       'seed': 0, 'missing': [channel]})
    result.append({'condition': 'channel_receipt_lifecycle', 'mechanism': 'whole_channel',
                   'seed': 0, 'missing': ['receipt', 'lifecycle']})
    for seed in SEEDS:
        for count in (1, 3, 5):
            rng = random.Random(str(seed) + '|' + unit_id + '|' + str(count))
            result.append({'condition': 'random_' + str(count), 'mechanism': 'random',
                           'seed': seed, 'missing': sorted(rng.sample(CHANNELS, count))})
    result.append({'condition': 'failure_correlated', 'mechanism': 'failure_stress',
                   'seed': 0, 'missing': ['receipt', 'lifecycle', 'failure'] if fault_event
                   else ['decision_reason']})
    return result
