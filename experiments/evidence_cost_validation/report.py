"""Join already sealed sweeps to old truth, report all strata, apply frozen Gate A."""
import argparse
from collections import defaultdict
from pathlib import Path

from experiments.evidence_contract_validation.common import ROOT, frozen_json, load_frozen, read_json, write_csv, write_json
from experiments.closeout_pilot.predictor import predict
from experiments.evidence_contract_validation.dependencies import project
from experiments.evidence_contract_validation.common import CHANNELS
from .audit import rows, verify
from .statistics import curves,compare,auc
from .sweep import inputs


def report(out):
    plan,masks=inputs(out);old=ROOT/plan['old_run'];results={};audits={};all_curves=[];all_family=[];pair_rows=[];full_rows=[];witnesses=[]
    for cost in ('C1','C2'):
        contract=plan['costs'][cost];results[cost]={};audits[cost]={}
        candidates=read_json(out/cost/'STATIC_CANDIDATES.json');selected=load_frozen(out/cost/'SELECTED_STATIC.json')['selected']
        for metric,order in selected.items():
            rr=[r for r in candidates if r['metric']==metric]
            best=max(rr,key=lambda r:(-r['wrong'],r['auc'] if r['auc'] is not None else 0,-r['weighted_decision_cost'],-r['candidate_index']))
            assert order==best['order']
            assert all(r['order'] in [c['order'] for c in plan['candidates'] if c['metric']==metric] for r in rr)
            for r in rr:assert auc({x['rho']:x['correct_coverage'] for x in r['curve']},contract['rho'])==r['auc']
        for split in ('development','heldout'):
            audits[cost][split]=verify(out,cost,split)
            # This is the first truth join for these sealed replay outputs.
            truth=read_json(old/'oracle'/f'{split}.json');data=list(rows(out/cost/f'{split}_PREDICTIONS.jsonl.gz'))
            docs=read_json(old/'licensed_source'/f'{split}.json');queries=read_json(old/f'{split}_QUERIES.json')
            scored={p:curves([r for r in data if r['policy']==p],truth,contract['rho']) for p in plan['policies']}
            results[cost][split]=compare(scored['dependency_guided'],scored['metric_static'],contract['rho'])
            if split=='development':
                for metric in selected:
                    actual=curves([r for r in data if r['policy']=='metric_static' and r['metric']==metric],truth,contract['rho'])
                    chosen=next(r for r in candidates if r['metric']==metric and r['order']==selected[metric])
                    assert actual['auc']==chosen['auc']
            for mechanism in ('ALL','whole_channel','random','failure_stress'):
                for metric in ('ALL','UEA','TaskSuccess','ALR','RIR'):
                    for policy in plan['policies']:
                        rr=[r for r in data if r['policy']==policy and (metric=='ALL' or r['metric']==metric) and (mechanism=='ALL' or r['mechanism']==mechanism)]
                        if not rr:continue
                        value=curves(rr,truth,contract['rho']);meta=dict(cost=cost,split=split,metric=metric,mechanism=mechanism,policy=policy)
                        all_curves.extend(meta|r for r in value['aggregate']);all_family.extend(meta|r for r in value['families'])
            by_pair=defaultdict(dict)
            for r in data:
                if r['policy']!='global_fixed':by_pair[(r['query_id'],r['condition'],r['seed'],r['rho'])][r['policy']]=r
            for key,pair in by_pair.items():
                s,d=pair['metric_static'],pair['dependency_guided'];t=truth[s['query_id']]
                sc=t['status']=='point' and s['status']=='point' and s['value']==t['value'];dc=t['status']=='point' and d['status']=='point' and d['value']==t['value']
                paired=dict(cost=cost,split=split,query_id=s['query_id'],unit=s['unit'],family_id=s['family_id'],metric=s['metric'],condition=s['condition'],seed=s['seed'],budget=s['budget'],rho=s['rho'],truth_status=t['status'],truth_value=t.get('value'),static_status=s['status'],dynamic_status=d['status'],static_correct=sc,dynamic_correct=dc,class_='benefit' if dc and not sc else 'harm' if sc and not dc else 'same')
                pair_rows.append(paired)
                if split=='heldout' and dc and not sc and 0<s['rho']<1:
                    c=next(c for c in masks[split][s['query_id']] if c['condition']==s['condition'] and c['seed']==s['seed'])
                    acquired=(set(CHANNELS)-set(c['missing']))|set(d['acquired_order'])
                    necessary=[]
                    for channel in d['acquired_order']:
                        removed=predict(s['metric'],project(docs[s['unit']],acquired-{channel}))
                        if removed['status']=='unknown':necessary.append(channel)
                    if necessary:witnesses.append(paired|dict(necessary_acquired_channels=necessary))
            for q in queries:
                full=predict(q['metric'],project(docs[q['unit']],set(CHANNELS)));t=truth[q['query_id']]
                maximum=[r for r in data if r['query_id']==q['query_id'] and r['rho']==1]
                assert all((r['status'],r['value'])==(full['status'],full['value']) for r in maximum),'Full endpoint disagreement'
                full_rows.append(dict(cost=cost,split=split,query_id=q['query_id'],metric=q['metric'],truth_status=t['status'],truth_value=t.get('value'),full_status=full['status'],full_value=full['value'],all_policy_mask_maxima_agree=True))
    attribution=load_frozen(out/'GAIN_ATTRIBUTION_SUMMARY.json');gates={}
    for cost in ('C1','C2'):
        value=results[cost]['heldout'];rr=[r for r in all_curves if r['cost']==cost and r['split']=='heldout' and r['metric']==r['mechanism']=='ALL']
        checks=dict(integrity=True,zero_wrong_and_wrong_safe=all(r['wrong']==r['wrong_safe']==0 for r in rr),
            positive_auc=value['difference'] is not None and value['difference']>1e-12,
            five_of_six=value['positive_families']>=5 and len(value['paired'])==6,
            all_leave_one_out_positive=all(r['difference']>1e-12 for r in value['leave_one_out']) and len(value['leave_one_out'])==6,
            interior_points=value['positive_interior_points']>=(2 if cost=='C1' else 1),
            dependency_recovery_witness=any(r['cost']==cost for r in witnesses))
        gates[cost]=dict(checks=checks,passed=all(checks.values()))
    passed=all(v['passed'] for v in gates.values())
    status='PASS' if passed else 'COST_SENSITIVE' if gates['C1']['passed'] and not gates['C2']['passed'] else 'NO_GAIN' if all(results[c]['heldout']['difference']<=1e-12 for c in ('C1','C2')) else 'SMALL_OR_UNSTABLE'
    gate=dict(status=status,passed=passed,costs=gates,new_sample_authorized=passed,new_business_executions=0,model_calls=0,
              subsequent_scope='Only preregistered 24 units plus bounded sanity/retry' if passed else 'STOP; R006-R008 NOT_RUN_GATE; no third cost or expansion')
    write_json(out/'TRAJECTORY_AUDIT.json',audits,exclusive=True)
    write_csv(out/'COST_CURVES.csv',all_curves);write_csv(out/'COST_PER_FAMILY.csv',all_family)
    write_csv(out/'COST_PAIRED_OUTCOMES.csv',pair_rows);write_csv(out/'FULL_COMPARATOR.csv',full_rows)
    write_json(out/'DEPENDENCY_RECOVERY_WITNESSES.json',witnesses,exclusive=True)
    frozen_json(out/'COST_ROBUSTNESS.json',dict(results=results,gate=gate,prior_C0=attribution['comparisons']['heldout'],
                costs=plan['costs'],new_business_executions=0,model_calls=0))
    frozen_json(out/'GATE_A.json',gate)
    print(dict(gate=gate,differences={c:results[c]['heldout']['difference'] for c in ('C1','C2')}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();report(a.out.resolve())
