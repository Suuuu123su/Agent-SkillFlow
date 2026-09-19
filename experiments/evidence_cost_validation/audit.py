"""Independent per-trajectory cost/order/projection audit, without executing policies."""
from collections import Counter
import gzip
import json

from experiments.evidence_contract_validation.common import ROOT, CHANNELS, canonical, load_frozen, read_json, sha
from experiments.evidence_contract_validation.dependencies import project, restoration_bundle
from experiments.closeout_pilot.predictor import predict
from .sweep import inputs


def rows(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:
        for line in f:yield json.loads(line)


def verify(out,cost,split):
    plan,masks=inputs(out);dest=out/cost;old=ROOT/plan['old_run'];contract=plan['costs'][cost]
    seal=load_frozen(dest/f'{split}_TRAJECTORY_SEAL.json')
    for name,digest in seal['files'].items():assert sha((dest/name).read_bytes())==digest,name
    assert seal['oracle_joined'] is False
    docs=read_json(old/'licensed_source'/f'{split}.json');queries={q['query_id']:q for q in read_json(old/f'{split}_QUERIES.json')}
    selected=load_frozen(dest/'SELECTED_STATIC.json')['selected'];wire_quotes=plan['costs']['C0']['quotes']
    masks={(qid,c['condition'],c['seed']):c for qid,cc in masks[split].items() for c in cc}
    views={r['sha256']:r['visible'] for r in rows(dest/f'{split}_VISIBLE_PROJECTIONS.jsonl.gz')}
    assert all(sha(canonical(v))==h for h,v in views.items())
    cache={};seen=set();count=0;statuses=Counter();headers_exceed_H=set()
    for r,ledger in zip(rows(dest/f'{split}_PREDICTIONS.jsonl.gz'),rows(dest/f'{split}_COST_LEDGER.jsonl.gz'),strict=True):
        assert r['row_id']==ledger['row_id'];q=queries[r['query_id']];doc=docs[q['unit']]
        assert all(r[k]==q[k] for k in ('unit','family_id','metric','source_id'))
        key=(r['query_id'],r['condition'],r['seed'],r['policy'],r['rho']);assert key not in seen;seen.add(key)
        i=contract['rho'].index(r['rho']);assert r['budget']==contract['budgets'][i]
        mask=masks[key[:3]];initial=set(CHANNELS)-set(mask['missing']);assert set(ledger['initial_channels'])==initial
        required=contract['public']+sum(contract['quotes'][c] for c in initial)
        header=canonical(dict(document=project(doc,set()),quotes=wire_quotes,transport='padded-canonical-v1'))
        required_wire=len(header)+sum(wire_quotes[c] for c in initial)
        if len(header)>plan['costs']['C1']['public']:headers_exceed_H.add(q['unit'])
        assert r['required_initial_cost']==required and r['required_initial_wire_bytes']==required_wire
        if required>r['budget']:
            assert r['status']=='infeasible' and not ledger['steps'] and not ledger['events'] and not ledger['feasible']
            assert r['decision_total']==r['wire_bytes']==ledger['decision_total']==ledger['wire_bytes']==0
        else:
            assert ledger['feasible'] and r['status']!='infeasible'
            acquired=set();decision=0;wire=0;acquisition=[]
            expected_kinds=[('public_header',None)]+[('initial',c) for c in CHANNELS if c in initial]
            expected_kinds += [('acquire',c) for c in r['acquired_order']]
            assert len(ledger['events'])==len(expected_kinds)
            for event,(kind,c) in zip(ledger['events'],expected_kinds,strict=True):
                assert event['kind']==kind and event['channel']==c
                if kind=='public_header':size=len(header);digest=sha(header);charge=contract['public']
                else:
                    assert c not in acquired
                    charge=contract['quotes'][c];size=wire_quotes[c]
                    assert decision+charge<=r['budget']
                    cache_key=(q['unit'],tuple(sorted(acquired)),c)
                    if cache_key not in cache:
                        bundle=restoration_bundle(doc,acquired,[c]);raw=canonical(dict(bundle=bundle,padding=''))
                        assert len(raw)<=size,'Frozen wire quote overflow'
                        encoded=canonical(dict(bundle=bundle,padding=' '*(size-len(raw))));assert len(encoded)==size
                        cache[cache_key]=sha(encoded)
                    digest=cache[cache_key];acquired.add(c)
                    if kind=='acquire':acquisition.append(c)
                decision+=charge;wire+=size
                assert (event['bytes'],event['sha256'],event['total'])==(size,digest,wire)
                assert (event['decision_cost'],event['decision_total'])==(charge,decision)
            assert decision==r['decision_total']==ledger['decision_total']<=r['budget']
            assert wire==r['wire_bytes']==ledger['wire_bytes']
            assert acquisition==r['acquired_order']
            before=set(initial);amount=required;wire_amount=required_wire
            assert len(ledger['steps'])==len(acquisition)+1
            order=list(CHANNELS) if r['policy']=='global_fixed' else selected[r['metric']]
            for step_index,step in enumerate(ledger['steps']):
                expected_view=project(doc,before);assert views[step['visible_sha256']]==expected_view
                assert set(step['acquired'])==before
                assert (step['decision_total'],step['remaining'],step['wire_total'])==(amount,r['budget']-amount,wire_amount)
                prediction=predict(r['metric'],expected_view);assert step['prediction']==prediction
                available=[c for c in order if c not in before and contract['quotes'][c]<=r['budget']-amount]
                if r['policy']=='dependency_guided':
                    preferred=[c for c in available if c in prediction['missing_channels']]
                    if preferred:available=preferred
                expected=None if prediction['status'] in ('point','not_applicable') or not available else available[0]
                assert step['selected']==expected
                if expected is None:
                    assert step_index==len(acquisition)
                    assert all(r[k]==prediction[k] for k in ('status','value','missing_channels','reason'))
                else:
                    assert acquisition[step_index]==expected
                    before.add(expected);amount+=contract['quotes'][expected];wire_amount+=wire_quotes[expected]
        count+=1;statuses[r['status']]+=1
    assert count==seal['rows']==len(queries)*20*len(plan['policies'])*len(contract['rho'])
    return dict(status='PASSED',rows=count,status_counts=dict(statuses),headers_exceed_H=sorted(headers_exceed_H),
                every_cost_order_projection_checked=True,oracle_access=False,new_executions=0,model_calls=0)
