"""Frozen new-batch analysis and Gate B, run only after both trajectory seals."""
import argparse
from collections import Counter,defaultdict
from pathlib import Path

from experiments.evidence_contract_validation.common import ROOT,CHANNELS,canonical,load_frozen,read_json,sha,write_csv,write_json,frozen_json
from experiments.evidence_contract_validation.dependencies import project
from experiments.evidence_contract_validation.independent_oracle import evaluate_unit
from experiments.closeout_pilot.predictor import predict
from experiments.closeout_pilot.reanalysis import check_map
from .audit import verify,rows
from .statistics import curves,compare


def summarize(out):
    plan=load_frozen(out/'FRESH_PLAN.json');check_map(ROOT,plan['source_hashes']);dest=out/'fresh'
    assert load_frozen(out/'GATE_A.json')['passed']
    complete=load_frozen(dest/'COLLECTION_COMPLETE.json')
    raw=load_frozen(dest/'RAW_AND_ORACLE_SEAL.json');check_map(dest/'raw',raw['files'])
    data_seal=load_frozen(dest/'DATASET_SEAL.json');check_map(dest,data_seal['files'])
    # Establish both sealed outputs before joining any full or independent truth.
    for cost in ('C1','C2'):
        seal=load_frozen(dest/cost/'heldout_TRAJECTORY_SEAL.json')
        assert seal['at']>data_seal['at']>raw['at']>plan['at']
        assert (dest/cost/'SELECTED_STATIC.json').read_bytes()==(out/cost/'SELECTED_STATIC.json').read_bytes()
    import json
    ledger=[json.loads(s) for s in (out/'EXECUTION_LEDGER.jsonl').read_text('utf-8').splitlines() if s]
    assert len(ledger)<=48 and [r['ordinal'] for r in ledger]==list(range(1,len(ledger)+1))
    assert all(r['model_calls']==0 for r in ledger)
    assert max(Counter(r['unit_id'] for r in ledger).values())<=2
    assert sum(r['phase']=='sanity' for r in ledger)<=4
    for r in ledger:
        if r['phase']=='formal':assert r['at']>plan['at']
    completed=[json.loads(s) for s in (dest/'COMPLETED.jsonl').read_text('utf-8').splitlines()]
    assert len(completed)==len({r['unit_id'] for r in completed})==24
    truth=read_json(dest/'oracle/heldout.json');queries=read_json(dest/'heldout_QUERIES.json')
    docs=read_json(dest/'licensed_source/heldout.json');assert len(queries)==len(truth)==48
    schedule={r['unit_id']:r for r in plan['schedule']};specs={r['execution_unit_id']:r for r in plan['specs']}
    effects=[];cell_checks=[]
    for r in completed:
        unit=r['unit_id'];folder=dest/r['raw'];independent=evaluate_unit(folder)
        assert independent==read_json(folder/'INDEPENDENT_ORACLE.json')
        assert sha(canonical(specs[unit]))==schedule[unit]['input_sha256']
        raw_spec=read_json(folder/'spec.json');assert {k:v for k,v in raw_spec.items() if not k.startswith('_')}==specs[unit]
        for metric in ('UEA','TaskSuccess'):assert independent['metrics'][metric]==truth[unit+':'+metric]
        cell=schedule[unit]['cell'];commit=cell.endswith('commit') and not cell.endswith('no_commit')
        expect_uea=cell=='invalid_commit';uea=truth[unit+':UEA'];task=truth[unit+':TaskSuccess']
        expected_match=uea['status']==task['status']=='point' and uea['value']==expect_uea and task['value']==commit
        cell_checks.append(expected_match)
        effects.append(dict(unit_id=unit,family_id=schedule[unit]['family_id'],cell=cell,raw=r['raw'],
            persistent_changes=r['effects'],UEA_status=uea['status'],UEA_value=uea['value'],
            TaskSuccess_status=task['status'],TaskSuccess_value=task['value'],four_cell_matches_expected=expected_match))
    results={};audits={};all_curves=[];family_curves=[];pairs=[];full_rows=[];benefit_families={}
    for cost in ('C1','C2'):
        audits[cost]=verify(dest,cost,'heldout');data=list(rows(dest/cost/'heldout_PREDICTIONS.jsonl.gz'));grid=plan['costs'][cost]['rho']
        scored={policy:curves([r for r in data if r['policy']==policy],truth,grid) for policy in ('global_fixed','metric_static','dependency_guided')}
        results[cost]=compare(scored['dependency_guided'],scored['metric_static'],grid)
        filters=[('ALL',lambda r:True),('UEA',lambda r:r['metric']=='UEA'),('TaskSuccess',lambda r:r['metric']=='TaskSuccess'),
                 ('UEA_true',lambda r:r['metric']=='UEA' and truth[r['query_id']]['status']=='point' and truth[r['query_id']]['value']==1),
                 ('UEA_false',lambda r:r['metric']=='UEA' and truth[r['query_id']]['status']=='point' and truth[r['query_id']]['value']==0),
                 ('TaskSuccess_true',lambda r:r['metric']=='TaskSuccess' and truth[r['query_id']]['status']=='point' and truth[r['query_id']]['value']==1),
                 ('TaskSuccess_false',lambda r:r['metric']=='TaskSuccess' and truth[r['query_id']]['status']=='point' and truth[r['query_id']]['value']==0)]
        for label,predicate in filters:
            for mechanism in ('ALL','whole_channel','random','failure_stress'):
                for policy in ('global_fixed','metric_static','dependency_guided'):
                    subset=[r for r in data if r['policy']==policy and predicate(r) and (mechanism=='ALL' or r['mechanism']==mechanism)]
                    if not subset:continue
                    value=curves(subset,truth,grid);meta=dict(cost=cost,stratum=label,mechanism=mechanism,policy=policy)
                    all_curves.extend(meta|r for r in value['aggregate']);family_curves.extend(meta|r for r in value['families'])
        matched=defaultdict(dict);gained=set()
        for r in data:
            if r['policy']!='global_fixed':matched[(r['query_id'],r['condition'],r['seed'],r['rho'])][r['policy']]=r
        for pp in matched.values():
            s,d=pp['metric_static'],pp['dependency_guided'];t=truth[s['query_id']]
            sc=t['status']=='point' and s['status']=='point' and s['value']==t['value'];dc=t['status']=='point' and d['status']=='point' and d['value']==t['value']
            if s['status']=='unknown' and dc and 0<s['rho']<1:gained.add(s['family_id'])
            pairs.append({k:s[k] for k in ('unit','family_id','query_id','metric','condition','mechanism','seed','rho','budget')}|
                dict(cost=cost,truth_status=t['status'],truth_value=t.get('value'),static_status=s['status'],dynamic_status=d['status'],
                     static_correct=sc,dynamic_correct=dc,class_='benefit' if dc and not sc else 'harm' if sc and not dc else 'same'))
        benefit_families[cost]=sorted(gained)
        for q in queries:
            full=predict(q['metric'],project(docs[q['unit']],set(CHANNELS)));t=truth[q['query_id']]
            top=[r for r in data if r['query_id']==q['query_id'] and r['rho']==1]
            assert all((r['status'],r['value'])==(full['status'],full['value']) for r in top)
            full_rows.append(dict(cost=cost,query_id=q['query_id'],metric=q['metric'],truth_status=t['status'],truth_value=t.get('value'),full_status=full['status'],full_value=full['value'],max_budget_agreement=True))
    no_errors=all(r['wrong']==r['wrong_safe']==0 for r in all_curves)
    checks={}
    for c in ('C1','C2'):
        v=results[c]
        checks[c]=dict(positive_auc=v['difference'] is not None and v['difference']>1e-12,
            five_of_six=v['positive_families']>=5,all_leave_one_out_positive=all(x['difference']>1e-12 for x in v['leave_one_out']),
            two_gain_families=len(benefit_families[c])>=2)
    replicated=all(cell_checks) and no_errors and all(all(v.values()) for v in checks.values())
    promise_points=sum(0<r['rho']<1 and r['coverage_difference']>=0.005 for r in results['C1']['curve'])
    promising=replicated and results['C1']['difference']>=0.001 and promise_points>=2
    if not all(cell_checks):status='INCONCLUSIVE'
    elif not no_errors:status='INVALID'
    elif promising:status='PROMISING_LIMITED'
    elif replicated:status='REPLICATED_SMALL_GAIN'
    elif all(results[c]['difference']<=1e-12 for c in ('C1','C2')):status='NO_GAIN'
    elif sum(results[c]['difference']>1e-12 for c in ('C1','C2'))==1:status='COST_SENSITIVE'
    else:status='SMALL_OR_UNSTABLE'
    gate=dict(status=status,replicated_small_gain=replicated,promising_limited=promising,checks=checks,
        complete_four_cells=all(cell_checks),no_additional_wrong_point_or_safe=no_errors,
        gain_families=benefit_families,C1_half_percentage_point_interior_budgets=promise_points,
        actual_executions=len(ledger),formal_units=24,sanity_executions=sum(r['phase']=='sanity' for r in ledger),
        retries=sum(r['attempt']==2 for r in ledger),cap=48,model_calls=0,judge_calls=0,paid_api_calls=0,
        next_step='Stop this confirmation batch; report magnitude and limitations; no automatic expansion')
    return dict(results=results,gate=gate,audits=audits,effects=effects,curves=all_curves,family_curves=family_curves,pairs=pairs,full=full_rows)


def report(out):
    result=summarize(out)
    write_json(out/'fresh/TRAJECTORY_AUDIT.json',result['audits'],exclusive=True)
    for name,key in [('FRESH_EFFECTS.csv','effects'),('FRESH_CURVES.csv','curves'),('FRESH_PER_FAMILY.csv','family_curves'),
                     ('FRESH_PAIRED_OUTCOMES.csv','pairs'),('FRESH_FULL_COMPARATOR.csv','full')]:write_csv(out/name,result[key])
    frozen_json(out/'FRESH_RESULTS.json',dict(results=result['results'],gate=result['gate'],raw_units=len(result['effects']),
        primary_queries=48,independent_truth_verified=True,new_families=False,source='new instances in preregistered old six families'))
    frozen_json(out/'GATE_B.json',result['gate'])
    print(dict(gate=result['gate'],differences={c:result['results'][c]['difference'] for c in ('C1','C2')}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();report(a.out.resolve())
