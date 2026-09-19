"""Adversarial byte-accounting and licensed-policy input checks; no task execution."""
import copy

import pytest

from experiments.evidence_contract_validation.common import CHANNELS, canonical
from experiments.evidence_contract_validation.dependencies import project
from experiments.evidence_contract_validation.evaluation import candidate_orders
from experiments.evidence_contract_validation.policy_worker import respond
from experiments.evidence_contract_validation.transport import Broker, padded_packet


def fixture():
    document = {'id': 'fixture', 'contract_version': 'controlled-persistent-effect-v1',
                'public': {'protocol': 'controlled-persistent-effect-v1'}}
    document.update({key: {'records': []} for key in CHANNELS})
    document['failure'] = {'monitor_closed': True, 'changes': [], 'operation': {'action': 'write'}}
    return document


def test_initial_and_returned_bytes_are_additive_and_atomic():
    doc = fixture()
    quotes = {channel: 32768 for channel in CHANNELS}
    broker = Broker(doc, {'grant'}, quotes)
    assert broker.total > quotes['grant']
    initial = broker.total
    prior = copy.deepcopy(broker.visible)
    with pytest.raises(ValueError, match='Over-budget'):
        broker.acquire('failure', initial + quotes['failure'] - 1)
    assert broker.total == initial and broker.visible == prior
    broker.acquire('failure', initial + quotes['failure'])
    assert broker.total == initial + quotes['failure']
    assert sum(event['bytes'] for event in broker.events) == broker.total
    assert broker.visible == project(doc, {'grant', 'failure'})


def test_padding_is_real_wire_bytes_and_overflow_never_truncates():
    raw = padded_packet({'value': '秘密'}, 300)
    assert len(raw) == 300
    with pytest.raises(ValueError, match='too small'):
        padded_packet({'value': '秘密'}, 5)


def test_worker_label_mutation_cannot_influence_answer():
    message = {'metric': 'UEA', 'visible': project(fixture(), {'failure'}),
               'policy': 'dependency_guided', 'acquired': ['failure'],
               'order': list(CHANNELS), 'quotes': {key: 100 for key in CHANNELS},
               'remaining': 500}
    original = respond(message)
    message.update(oracle={'value': True}, Full={'value': False}, hidden_documents={'secret': 'changed'})
    assert respond(message) == original
    assert original['prediction']['value'] is False


def test_candidate_cap_does_not_force_receipt_first():
    orders = candidate_orders('UEA', {key: 100 for key in CHANNELS})
    assert len(orders) <= 24
    assert {'receipt', 'failure', 'grant', 'lifecycle', 'scope_lifetime'} <= {order[0] for order in orders}
