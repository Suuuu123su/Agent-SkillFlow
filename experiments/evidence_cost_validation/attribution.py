"""Full C0 pair attribution from previously sealed records, including losses."""
from collections import defaultdict
import argparse
import csv
import gzip
import json
from pathlib import Path

from experiments.evidence_contract_validation.common import ROOT, CHANNELS, canonical, frozen_json, read_json, sha, write_csv, write_json
from experiments.evidence_contract_validation.dependencies import project
from experiments.evidence_contract_validation.policy import choose
from experiments.evidence_contract_validation.transport import Broker
from experiments.closeout_pilot.predictor import predict
from .statistics import curves, compare, auc
from .sweep import inputs


def read_gz(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:
        for line in f:yield json.loads(line)


def run(out):
    plan,masks=inputs(out);old=ROOT/plan['old_run'];corrected=ROOT/plan['corrected_run']
    if (out/'GAIN_ATTRIBUTION.csv.gz').exists():raise FileExistsError('Preserve prior attribution')
    budget_grid=plan['costs']['C0']['budgets'];grid=plan['costs']['C0']['rho'];quotes=plan['costs']['C0']['quotes']
    contributions=[];group_rows=[];comparisons={};all_pairs=[];views={};control_count=0
    case_pool=[]
    for split in ('development','heldout'):
        truth=read_json(old/'oracle'/f'{split}.json');docs=read_json(old/'licensed_source'/f'{split}.json')
        records=[r|dict(rho=r['budget']/budget_grid[-1]) for r in read_gz(corrected/f'{split}_PREDICTIONS.jsonl.gz') if r['policy'] in ('metric_static','dependency_guided')]
        measured={p:curves([r for r in records if r['policy']==p],truth,grid) for p in ('metric_static','dependency_guided')}
        comparisons[split]=compare(measured['dependency_guided'],measured['metric_static'],grid)
        denom={(r['family_id'],r['rho']):r['reference_point'] for r in measured['metric_static']['families']}
        families=len({r['family_id'] for r in records});by_key=defaultdict(dict)
        for r in records:by_key[(r['query_id'],r['condition'],r['seed'],r['budget'])][r['policy']]=r
        mask_index={(qid,c['condition'],c['seed']):c for qid,cc in masks[split].items() for c in cc}
        selected=read_json(corrected/'CLOSEOUT_PLAN.json')['selected_static']
        group_curves=defaultdict(lambda:defaultdict(float))
        for key,pair in sorted(by_key.items()):
            s,d=pair['metric_static'],pair['dependency_guided'];t=truth[s['query_id']];qualified=t['status']=='point'
            sc=qualified and s['status']=='point' and s['value']==t['value'];dc=qualified and d['status']=='point' and d['value']==t['value']
            delta=int(dc)-int(sc);label='benefit' if delta>0 else 'harm' if delta<0 else 'same'
            condition=mask_index[key[:3]];initial=set(CHANNELS)-set(condition['missing']);doc=docs[s['unit']]
            so,do=s['acquired_order'],d['acquired_order'];common=[]
            for left,right in zip(so,do):
                if left!=right:break
                common.append(left)
            different=so!=do;missing=[];digest=None;sn=dn=None;group='no_divergence';remaining=None
            if different:
                assert len(common)<len(so) and len(common)<len(do),'Same observation cannot stop in only one policy'
                broker=Broker(doc,initial,quotes)
                for c in common:broker.acquire(c,s['budget'])
                prediction=predict(s['metric'],broker.visible);missing=prediction['missing_channels']
                sn,dn=so[len(common)],do[len(common)];remaining=s['budget']-broker.total
                order=selected[s['metric']]
                assert choose(s['metric'],'metric_static',prediction,broker.acquired,order,quotes,remaining)==sn
                assert choose(s['metric'],'dependency_guided',prediction,broker.acquired,order,quotes,remaining)==dn
                assert choose(s['metric'],'dependency_guided',prediction|{'missing_channels':[]},broker.acquired,order,quotes,remaining)==sn
                control_count+=1
                digest=sha(canonical(broker.visible));views.setdefault(digest,broker.visible)
                group={'lifecycle':'lifecycle_session','receipt':'receipt_execution','failure':'receipt_execution',
                       'grant':'grant_scope','scope_lifetime':'grant_scope','task_success_evidence':'task_completion'}.get(dn,'other')
            weight=1/3 if s['mechanism']=='random' else 1
            den=denom[s['family_id'],s['rho']];value=delta*weight/den/families if qualified and den else 0.0
            for dimension,category in [('dependency',group),('metric',s['metric']),('condition',s['condition']),('family',s['family_id']),('sign',label),('mechanism',s['mechanism'])]:
                group_curves[dimension,category][s['rho']]+=value
            row={k:s[k] for k in ('split','family_id','unit','query_id','metric','condition','mechanism','seed','budget','rho')}
            j=grid.index(s['rho']);area_weight=((grid[j]-grid[j-1])/2 if j else 0)+((grid[j+1]-grid[j])/2 if j<len(grid)-1 else 0)
            row.update(weighted_auc_contribution=value*area_weight,truth_status=t['status'],truth_value=t.get('value'),static_status=s['status'],dynamic_status=d['status'],
                static_value=s['value'],dynamic_value=d['value'],static_correct=sc,dynamic_correct=dc,class_=label,
                static_order=json.dumps(so),dynamic_order=json.dumps(do),static_cost=s['charged_total_bytes'],dynamic_cost=d['charged_total_bytes'],
                first_common_prefix=json.dumps(common),first_visible_sha256=digest,first_missing=json.dumps(missing),
                static_first_choice=sn,dynamic_first_choice=dn,remaining_at_divergence=remaining,
                final_static_missing=json.dumps(s['missing_channels']),final_dynamic_missing=json.dumps(d['missing_channels']),
                dependency_group=group,weighted_coverage_delta=value)
            all_pairs.append(row)
            if split=='heldout':case_pool.append((row,doc,initial,so,do))
        for dimension in ('dependency','metric','condition','family','sign','mechanism'):
            areas=[]
            for (dim,category),values in sorted(group_curves.items()):
                if dim!=dimension:continue
                area=auc({x:values[x] for x in grid},grid);areas.append(area)
                group_rows.append(dict(split=split,dimension=dimension,category=category,auc_contribution=area))
            assert abs(sum(areas)-comparisons[split]['difference'])<1e-10,dimension
        delta_curve={r['rho']:r['coverage_difference'] for r in comparisons[split]['curve']}
        area_sum=0
        for j,(a,b) in enumerate(zip(grid,grid[1:])):
            area=(delta_curve[a]+delta_curve[b])/2*(b-a);area_sum+=area
            contributions.append(dict(split=split,left_budget=budget_grid[j],right_budget=budget_grid[j+1],left_delta=delta_curve[a],right_delta=delta_curve[b],auc_contribution=area))
        assert abs(area_sum-comparisons[split]['difference'])<1e-10
    expected=read_json(corrected/'CLOSEOUT_RESULTS.json')['dynamic_vs_static']['auc_difference']
    assert abs(comparisons['heldout']['difference']-expected)<1e-10
    published=read_json(corrected/'CLOSEOUT_RESULTS.json')['dynamic_vs_static']
    for actual,prior in zip(comparisons['heldout']['paired'],published['paired_families'],strict=True):
        assert actual['family_id']==prior['family_id'] and abs(actual['difference']-prior['difference'])<1e-10
    for actual,prior in zip(comparisons['heldout']['curve'],published['budgets'],strict=True):
        assert abs(actual['coverage_difference']-prior['correct_coverage_difference'])<1e-10
        assert actual['dynamic_wrong']==actual['static_wrong']==actual['dynamic_wrong_safe']==actual['static_wrong_safe']==0
    with gzip.open(out/'GAIN_ATTRIBUTION.csv.gz','wt',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(all_pairs[0]));w.writeheader();w.writerows(all_pairs)
    write_csv(out/'BUDGET_CONTRIBUTIONS.csv',contributions);write_csv(out/'GROUP_CONTRIBUTIONS.csv',group_rows)
    with gzip.open(out/'ATTRIBUTION_VISIBLE_PROJECTIONS.jsonl.gz','wt',encoding='utf-8') as f:
        for digest,view in sorted(views.items()):f.write(canonical(dict(sha256=digest,visible=view)).decode()+'\n')
    chosen=[]
    for label in ('benefit','harm','same'):
        candidates=[v for v in case_pool if v[0]['class_']==label]
        if candidates:
            value=sorted(candidates,key=lambda v:(-abs(v[0]['weighted_auc_contribution']),v[0]['query_id'],v[0]['condition'],v[0]['seed'],v[0]['budget']))[0]
            chosen.append((label,value))
    known=[v for v in case_pool if v[0]['unit']=='H01_publish_directory_02' and v[0]['metric']=='UEA' and v[0]['condition']=='random_3' and v[0]['seed']==19121 and v[0]['budget']==66121]
    if known:chosen.append(('known_lifecycle_counterexample',known[0]))
    cases=[]
    for label,(row,doc,initial,so,do) in chosen[:4]:
        acquired=initial|set(do);before=predict(row['metric'],project(doc,acquired));tests=[]
        for c in sorted(acquired):
            after=predict(row['metric'],project(doc,acquired-{c}))
            tests.append(dict(channel=c,before=before,after=after,point_to_unknown=before['status']=='point' and after['status']=='unknown'))
        cases.append(dict(role=label,pair=row,offline_prerequisite_deletions=tests,oracle_unchanged=True))
    write_json(out/'REPRESENTATIVE_CASES.json',cases,exclusive=True)
    result=dict(status='ATTRIBUTION_RECONCILED',comparisons=comparisons,expected_heldout_delta=expected,
        pair_rows=len(all_pairs),priority_disabled_controls=control_count,
        dependency_recovery_witness=any(t['point_to_unknown'] for c in cases if c['role']=='benefit' for t in c['offline_prerequisite_deletions']),
        classes={split:{label:sum(r['split']==split and r['class_']==label for r in all_pairs) for label in ('benefit','harm','same')} for split in ('development','heldout')},
        change_table_missing_fields=['family','unit','metric','condition','seed','first_visible','first_missing','reference_correctness'],
        source='Reconstructed from complete sealed corrected predictions, documents and mask manifest; ROW_CHANGES alone insufficient',
        reconciliation_tolerance=1e-10,new_business_executions=0,model_calls=0)
    frozen_json(out/'GAIN_ATTRIBUTION_SUMMARY.json',result)
    print({k:v for k,v in result.items() if k not in ('comparisons',)})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
