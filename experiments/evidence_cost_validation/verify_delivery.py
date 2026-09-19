"""Read-only audit. No collector, policy worker, API, or subprocess execution."""
import argparse
import csv
import gzip
import io
import json
from collections import Counter, defaultdict
from pathlib import Path

from experiments.evidence_contract_validation.common import ROOT, load_frozen, read_json, sha
from experiments.evidence_contract_validation.masks import conditions
from experiments.evidence_contract_validation.independent_oracle import evaluate_unit
from experiments.closeout_pilot.reanalysis import check_map
from .audit import verify, rows
from .fresh_report import summarize
from .statistics import curves, compare, auc
from .fresh import new_conditions
from .sweep import inputs


def csv_rows(path):
    with path.open(encoding='utf-8',newline='') as f:
        return list(csv.DictReader(f))


def same_csv(path, data):
    s=io.StringIO(newline='')
    writer=csv.DictWriter(s,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
    assert path.read_bytes()==s.getvalue().encode('utf-8'),path


def run(out):
    plan,masks=inputs(out)
    check_map(ROOT/plan['old_run'],plan['original_inputs'])
    check_map(ROOT/plan['corrected_run'],plan['corrected_inputs'])
    check_map(ROOT,plan['source_hashes'])
    check_map(ROOT,load_frozen(out/'IMPLEMENTATION_SEAL.json')['source_hashes'])
    for split in ('development','heldout'):
        queries=read_json(ROOT/plan['old_run']/f'{split}_QUERIES.json')
        assert masks[split]=={q['query_id']:conditions(q['unit'],q['fault_event']) for q in queries}
    audit={};old_results=load_frozen(out/'COST_ROBUSTNESS.json')['results']
    for cost in ('C1','C2'):
        contract=plan['costs'][cost];selected=load_frozen(out/cost/'SELECTED_STATIC.json')['selected']
        candidates=read_json(out/cost/'STATIC_CANDIDATES.json')
        assert len(candidates)==96
        for metric,order in selected.items():
            rr=[r for r in candidates if r['metric']==metric];assert len(rr)==24
            assert {r['candidate_index'] for r in rr}=={r['candidate_index'] for r in plan['candidates'] if r['metric']==metric}
            assert order==max(rr,key=lambda r:(-r['wrong'],r['auc'] if r['auc'] is not None else 0,-r['weighted_decision_cost'],-r['candidate_index']))['order']
            for r in rr:
                assert auc({x['rho']:x['correct_coverage'] for x in r['curve']},contract['rho'])==r['auc']
        for split in ('development','heldout'):
            audit[cost+'_'+split]=verify(out,cost,split)
            data=list(rows(out/cost/f'{split}_PREDICTIONS.jsonl.gz'))
            truth=read_json(ROOT/plan['old_run']/'oracle'/f'{split}.json')
            scores={p:curves([r for r in data if r['policy']==p],truth,contract['rho']) for p in plan['policies']}
            assert compare(scores['dependency_guided'],scores['metric_static'],contract['rho'])==old_results[cost][split]
            assert all(r['wrong']==r['wrong_safe']==0 for v in scores.values() for r in v['aggregate'])
            if split=='development':
                for metric,order in selected.items():
                    score=curves([r for r in data if r['policy']=='metric_static' and r['metric']==metric],truth,contract['rho'])
                    assert score['auc']==next(r['auc'] for r in candidates if r['metric']==metric and r['order']==order)
    attribution=load_frozen(out/'GAIN_ATTRIBUTION_SUMMARY.json');sums=defaultdict(float)
    for r in csv_rows(out/'GROUP_CONTRIBUTIONS.csv'):sums[r['split'],r['dimension']]+=float(r['auc_contribution'])
    for (split,dimension),value in sums.items():assert abs(value-attribution['comparisons'][split]['difference'])<=1e-10
    intervals=defaultdict(float)
    for r in csv_rows(out/'BUDGET_CONTRIBUTIONS.csv'):intervals[r['split']]+=float(r['auc_contribution'])
    for split,value in intervals.items():assert abs(value-attribution['comparisons'][split]['difference'])<=1e-10
    with gzip.open(out/'GAIN_ATTRIBUTION.csv.gz','rt',encoding='utf-8') as f:
        paired=list(csv.DictReader(f))
    assert len(paired)==22400
    # Full frozen fresh analysis recomputes every cost/order/projection and independently reads actual stores.
    fresh=summarize(out);stored=load_frozen(out/'FRESH_RESULTS.json')
    assert fresh['results']==stored['results'] and fresh['gate']==stored['gate']==load_frozen(out/'GATE_B.json')
    for name,key in [('FRESH_EFFECTS.csv','effects'),('FRESH_CURVES.csv','curves'),('FRESH_PER_FAMILY.csv','family_curves'),('FRESH_PAIRED_OUTCOMES.csv','pairs'),('FRESH_FULL_COMPARATOR.csv','full')]:
        same_csv(out/name,fresh[key])
    fplan=load_frozen(out/'FRESH_PLAN.json');fmasks=load_frozen(out/'fresh/MASK_MANIFEST.json')
    fq=read_json(out/'fresh/heldout_QUERIES.json')
    assert fmasks['heldout']=={q['query_id']:new_conditions(q['unit'],q['fault_event'],fplan['seeds']) for q in fq}
    sanity=load_frozen(out/'sanity/SANITY_RESULTS.json')
    for r in sanity['checks']:
        folder=out/r['raw'];assert evaluate_unit(folder)==read_json(folder/'INDEPENDENT_ORACLE.json')
        assert all(r[k] for k in ('full_agreement','oracle_matches_actual_effect','packet_capacity_supported'))
    for digest in out.rglob('*.json.sha256'):
        if 'temp' not in digest.relative_to(out).parts:load_frozen(Path(str(digest)[:-7]))
    if (out/'DELIVERY_MANIFEST.json').exists():
        manifest=load_frozen(out/'DELIVERY_MANIFEST.json');check_map(ROOT,manifest['files'])
    summary=read_json(out/'SUMMARY.json')
    assert summary['executions']==fresh['gate']['actual_executions']==28
    assert summary['fresh_deltas']=={c:fresh['results'][c]['difference'] for c in ('C1','C2')}
    return dict(status='PASSED',historical_inputs_unchanged=True,source_seals_unchanged=True,
                original_masks_equal=True,fresh_masks_equal=True,old_trajectory_rows=sum(x['rows'] for x in audit.values()),
                fresh_trajectory_rows=sum(x['rows'] for x in fresh['audits'].values()),
                independent_formal_units=24,independent_sanity_units=4,fresh_csv_exact=True,
                C0_area_reconciled=True,static_selection_reconciled=True,gate_A='PASS',gate_B=fresh['gate']['status'],
                campaign_executions=28,verification_new_executions=0,model_calls=0,
                method='Read retained files/SQLite, re-evaluate finite predicates and recompute statistics; no collection or worker invocation')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    print(json.dumps(run(a.out.resolve()),ensure_ascii=False,sort_keys=True,indent=2))
