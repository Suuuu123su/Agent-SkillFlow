"""Contract tests only; no subprocess task actions or model calls."""
import pytest

from experiments.evidence_contract_validation.common import ROOT, CHANNELS, read_json
from experiments.evidence_contract_validation.dependencies import project
from experiments.closeout_pilot.policy_worker import respond
from experiments.evidence_cost_validation.costs import CostBroker, trial
from experiments.evidence_cost_validation.registration import OLD
from experiments.evidence_cost_validation.statistics import curves


@pytest.fixture
def source():
    old=ROOT/OLD
    return next(iter(read_json(old/'licensed_source/development.json').values())),read_json(old/'FINAL_PLAN.json')['quotes']


class LocalWorker:
    def __init__(self):self.seen=[]
    def ask(self,message):self.seen.append(message);return respond(message)


def contract():return dict(public=1,quotes={c:1 for c in CHANNELS})


def test_proxy_one_is_never_used_as_wire_packet_capacity(source):
    doc,quotes=source;b=CostBroker(doc,set(),contract(),quotes)
    b.acquire('receipt',2)
    assert b.total==2 and b.wire.total>quotes['receipt']
    assert b.events[-1]['decision_cost']==1 and b.events[-1]['bytes']==quotes['receipt']
    assert b.wire.visible==project(doc,{'receipt'})


def test_unauthorized_budget_never_fetches_unpurchased_bundle(source):
    doc,quotes=source;b=CostBroker(doc,set(),contract(),quotes)
    def forbidden(*args):raise AssertionError('payload accessed before budget check')
    b.wire.acquire=forbidden
    with pytest.raises(ValueError):b.acquire('grant',1)


def test_infeasible_initial_observation_never_reaches_policy(source):
    doc,quotes=source;worker=LocalWorker()
    prediction,broker,steps=trial(worker,doc,'UEA',set(CHANNELS),contract(),quotes,9,'metric_static',list(CHANNELS),trace=True)
    assert prediction['status']=='infeasible' and not worker.seen and not steps
    assert broker.initial_cost==10


@pytest.mark.parametrize('policy',['global_fixed','metric_static','dependency_guided'])
def test_full_budget_matches_full_without_free_initial_evidence(source,policy):
    doc,quotes=source;worker=LocalWorker()
    prediction,broker,steps=trial(worker,doc,'UEA',set(),contract(),quotes,10,policy,list(CHANNELS),trace=True)
    expected=respond(dict(metric='UEA',visible=project(doc,set(CHANNELS)),policy=policy,acquired=list(CHANNELS),order=list(CHANNELS),quotes=quotes,remaining=0))['prediction']
    assert prediction==expected and broker.total<=10
    assert set(worker.seen[0]['visible'])==set(project(doc,set()))
    assert worker.seen[0]['quotes']=={c:1 for c in CHANNELS}
    assert 'oracle' not in worker.seen[0] and 'condition' not in worker.seen[0]


def test_family_seed_weighting_and_infeasible_denominator():
    records=[];truth={q:dict(status='point',value=True) for q in ('q1','q2')}
    for rho in (0,1):
        for seed,status in enumerate(['point','unknown','infeasible']):
            records.append(dict(family_id='f1',query_id='q1',condition='random_3',seed=seed,rho=rho,metric='UEA',status=status if rho else 'infeasible',value=True if rho and status=='point' else None))
        records.append(dict(family_id='f2',query_id='q2',condition='channel_receipt',seed=0,rho=rho,metric='UEA',status='point' if rho else 'infeasible',value=True if rho else None))
    scored=curves(records,truth,[0,1])
    assert scored['aggregate'][1]['correct_coverage']==pytest.approx(2/3)
    assert scored['auc']==pytest.approx(1/3)
    assert scored['aggregate'][0]['infeasible_rate']==1
