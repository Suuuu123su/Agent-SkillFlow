"""Unchanged licensed evidence and policy semantics; separate proxy/wire books."""
from experiments.evidence_contract_validation.common import CHANNELS, canonical, sha
from experiments.evidence_contract_validation.transport import Broker


class CostBroker:
    def __init__(self, document, initial, contract, wire_quotes):
        self.wire = Broker(document, initial, wire_quotes)
        self.contract = contract
        self.quotes = contract['quotes']
        self.total = contract['public'] + sum(self.quotes[c] for c in initial)
        self.initial_cost = self.total
        self.events = []
        amount = 0
        for event in self.wire.events:
            cost = contract['public'] if event['kind']=='public_header' else self.quotes[event['channel']]
            amount += cost
            self.events.append(event | dict(decision_cost=cost, decision_total=amount))
        assert amount == self.total

    def acquire(self, channel, budget):
        # Reject using only public quotes before accessing the unpurchased bundle.
        if channel in self.wire.acquired or self.total+self.quotes[channel]>budget:
            raise ValueError('Duplicate or unaffordable acquisition')
        self.wire.acquire(channel, self.wire.total+self.wire.quotes[channel])
        self.total += self.quotes[channel]
        self.events.append(self.wire.events[-1] | dict(decision_cost=self.quotes[channel], decision_total=self.total))


def trial(worker, document, metric, initial, contract, wire_quotes, budget, policy, order,
          views=None, trace=False):
    broker = CostBroker(document, initial, contract, wire_quotes)
    if broker.total > budget:
        return dict(status='infeasible', value=None, missing_channels=[], reason='budget_below_common_initial_payload'),broker,[]
    steps=[]
    while True:
        message=dict(metric=metric, visible=broker.wire.visible, policy=policy,
                     acquired=sorted(broker.wire.acquired), order=order,
                     quotes=broker.quotes, remaining=budget-broker.total)
        answer=worker.ask(message)
        if trace:
            digest=sha(canonical(broker.wire.visible))
            if views is not None:views.setdefault(digest,broker.wire.visible)
            steps.append(dict(acquired=message['acquired'],visible_sha256=digest,
                              remaining=message['remaining'],decision_total=broker.total,
                              wire_total=broker.wire.total,**answer))
        channel=answer['selected']
        if channel is None:return answer['prediction'],broker,steps
        broker.acquire(channel,budget)
