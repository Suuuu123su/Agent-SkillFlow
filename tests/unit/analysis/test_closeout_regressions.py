"""Offline regression tests; no sandbox scenario is executed."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.closeout_pilot.paths import confined
from experiments.closeout_pilot.predictor import predict
from experiments.evidence_contract_validation.dependencies import project, restoration_bundle, apply_bundle
from experiments.evidence_contract_validation.common import CHANNELS
from experiments.evidence_contract_validation.policy import choose
from experiments.evidence_contract_validation.reporting import _auc


@pytest.mark.parametrize('relative', ['raw/heldout/a.json', r'raw\heldout\a.json'])
def test_portable_relative_paths(tmp_path, relative):
    assert confined(tmp_path, relative) == tmp_path / 'raw' / 'heldout' / 'a.json'


@pytest.mark.parametrize('relative', ['', '/etc/passwd', r'\root', r'\\host\share',
                                    'C:/test', 'C:test', '../test', 'raw/../test',
                                    r'raw\..\test', 'raw//test', 'raw/./test', 'a:stream'])
def test_reject_unsafe_paths(tmp_path, relative):
    with pytest.raises(ValueError):
        confined(tmp_path, relative)


def test_reject_resolved_link_escape(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    try:
        (root / 'link').symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Host cannot create test symlink')
    with pytest.raises(ValueError):
        confined(root, 'link/data')


def receipt_document():
    op = dict(action='write', resource='target', task_id='task', session_id='session',
              effect_id='effect', attempt_id='attempt', started_ns=100, finished_ns=200)
    ack = {k:v for k,v in op.items() if k not in ('started_ns', 'finished_ns')}
    ack.update(status='committed', time_ns=150)
    return {'receipt':{'operation':op, 'ack':ack}, 'grant':{'closed':True,'records':[]}}


def test_hidden_session_requires_charged_lifecycle_restoration():
    document = receipt_document()
    channels = set(CHANNELS) - {'lifecycle', 'failure'}
    masked = project(document, channels)
    result = predict('UEA', masked)
    assert result['status'] == 'unknown'
    assert 'lifecycle' in result['missing_channels']
    selected = choose('UEA', 'dependency_guided', result, channels,
                      ['lifecycle','failure'], {'lifecycle':1,'failure':10}, 1)
    assert selected == 'lifecycle'
    restored = apply_bundle(masked, restoration_bundle(document, channels, selected))
    assert predict('UEA', restored)['value'] is True


@pytest.mark.parametrize('field', ['action','resource','session_id','effect_id','task_id','attempt_id'])
def test_invalid_binding_stays_unknown_after_restore(field):
    document = receipt_document()
    document['receipt']['ack'][field] = 'wrong'
    assert predict('UEA', project(document, CHANNELS))['status'] == 'unknown'


@pytest.mark.parametrize('time', [99,201])
def test_expired_receipt_stays_unknown(time):
    document = receipt_document()
    document['receipt']['ack']['time_ns'] = time
    assert predict('UEA', document)['status'] == 'unknown'


def test_uneven_budget_auc_reverses_equal_point_ranking(monkeypatch, tmp_path):
    from experiments.closeout_pilot import evaluation as ev
    budgets = [0,1,10]
    a, b = [1,0,0], [0,0,1]
    assert sum(a) == sum(b)
    assert _auc([{'x':x,'y':y} for x,y in zip(budgets,a)],'x','y',budgets) == .05
    assert _auc([{'x':x,'y':y} for x,y in zip(budgets,b)],'x','y',budgets) == .45
    monkeypatch.setattr(ev,'Worker',lambda cwd:SimpleNamespace(close=lambda:None))
    monkeypatch.setattr(ev,'conditions',lambda *args:[{'missing':[], 'mechanism':'whole'}])
    def evaluate(worker, doc, metric, visible, quotes, budget, policy, order):
        good = (budget == 0 if order[0] == 'a' else budget == 10)
        return {'status':'point' if good else 'unknown','value':True if good else None}, SimpleNamespace(total=0)
    monkeypatch.setattr(ev,'evaluate_one',evaluate)
    selected, rows = ev.choose_static({'u':{}}, [{'metric':'UEA','unit':'u','query_id':'q','family_id':'f','fault_event':False}],
                                     {},budgets,{'q':{'status':'point','value':True}},tmp_path/'ipc',
                                     [{'metric':'UEA','candidate_index':0,'order':['a']},
                                      {'metric':'UEA','candidate_index':1,'order':['b']}])
    assert selected['UEA'] == ['b']
    assert rows[1]['family_equal_coverage_auc'] == .45
