"""Independent count/interval check and source-based finite non-identifiability witnesses."""
from common import *
from collections import Counter
from itertools import product
import sqlite3,copy

def main():
 guard();reg={r['query_id']:r for r in rows(OUT/'QUERY_REGISTRY.jsonl')};base={p['query_id']:p for p in rows(OUT/'results/V00.jsonl')};checks=[];conn=sqlite3.connect(':memory:');conn.execute('create table p(view text, q text, status text, elig integer, value text)');transitions=[];monotonic=[];fullsum=rows(OUT/'P4_METRIC_MAIN.jsonl')
 for i in range(13):
  vid=f'V{i:02}';rr=rows(OUT/f'results/{vid}.jsonl');conn.executemany('insert into p values (?,?,?,?,?)',[(vid,x['query_id'],x['status'],x['eligibility'],canonical(x['value'])) for x in rr])
  counts=dict(conn.execute('select status,count(*) from p where view=? group by status',(vid,)).fetchall());reported=Counter()
  for s in fullsum:
   if s['view_id']==vid:
    for k in ['point','bounded','unknown','not_applicable','conflict','analysis_error']:reported[k]+=s[k]
  checks.append(dict(check='SQL_status_counts',view=vid,pass_check=all(counts.get(k,0)==v for k,v in reported.items()),computed=counts,reported=dict(reported)))
  for p in rr:
   b=base[p['query_id']]
   if i in range(1,11) and ((b['status'] in ['unknown','bounded'] and p['status']=='point') or (b['status']=='point' and p['status']=='point' and p['value']!=b['value'])):monotonic.append(dict(view=vid,query_id=p['query_id'],before=b['value'],after=p['value'],before_status=b['status']))
   if p['metric']=='HIAA_run' and p['eligibility'] is True:
    cells=p['details']['cells'];ln=un=0
    for name,sign in [('p11',1),('p10',-1),('p01',-1),('p00',1)]:
     c=cells[name];lo=c['true']/c['denominator'];hi=(c['true']+c['unknown'])/c['denominator'];ln+=sign*(lo if sign>0 else hi);un+=sign*(hi if sign>0 else lo)
    checks.append(dict(check='HIAA_signed_bounds',view=vid,query_id=p['query_id'],pass_check=abs(ln-p['lower'])<1e-12 and abs(un-p['upper'])<1e-12))
 # All four-cell singleton-known/unknown combinations: brute Boolean completions prove interval sign handling.
 for vals in product([0,1,None],repeat=4):
  possible=[a-b-c+d for a,b,c,d in product([0,1],repeat=4) if all(v is None or v==w for v,w in zip(vals,[a,b,c,d]))];lo=sum(sign*(0 if v is None and sign>0 else 1 if v is None else v) for v,sign in zip(vals,[1,-1,-1,1]));hi=sum(sign*(1 if v is None and sign>0 else 0 if v is None else v) for v,sign in zip(vals,[1,-1,-1,1]));checks.append(dict(check='HIAA_81_completion_vectors',inputs=vals,pass_check=(lo==min(possible) and hi==max(possible))))
 byid={d['id']:d for d in rows(OUT/'minimal_data/BASE_DOCUMENTS.jsonl')};g={x['query_id']:x for x in rows(OUT/'GOLD_PROVENANCE.jsonl')};qbyname={r['native_unit_ref']:r for r in reg.values() if r['metric']=='HIAA_pot_declared'};qs={q['query_id']:q for q in rows(OUT/'minimal_data/PREDICTOR_QUERIES.jsonl')};witness=[]
 from views import project
 pairs=[('V02','unexecuted_but_reachable','authorized_excluded_from_U'),('V10','unexecuted_but_reachable','same_sets_true_zero')]
 for vid,a,b in pairs:
  ra=qbyname[a];rb=qbyname[b];qa=qs[ra['query_id']];qb=qs[rb['query_id']];da=project(byid[qa['unit']],vid);db=project(byid[qb['unit']],vid);da['id']=db['id']='opaque-common-identity';assert da==db;ga=g[ra['query_id']]['value'];gb=g[rb['query_id']]['value'];assert ga!=gb
  witness.append(dict(view_id=vid,type='existing_saved_finite_model_pair_modulo_opaque_identity_bijection',source_a=ra['source_ref'],source_b=rb['source_ref'],query_a=ra['query_id'],query_b=rb['query_id'],truth_a=ga,truth_b=gb,visible_a=da,visible_b=db,visible_hash=digest(da),observations_equal=True,new_model_or_tool_runs=0,independent_reference='exhaustive state-transition relation'))
 # Real raw grant_snapshot duplicate exists; both it and derivative flags are absent from actual projected views.
 raw=next(x for x in rows(OUT/'control/REFERENCE_INPUTS.jsonl') if x['kind']=='reference');rawcount=sum('grant_snapshot' in e for s in raw['states'].values() for e in s['events']);mask=(OUT/'views/full/V02/DOCUMENTS.jsonl').read_text(encoding='utf-8');assert rawcount>0;assert 'grant_snapshot' not in mask and 'matched_grants' not in mask and '"authorized"' not in mask
 checks.append(dict(check='real_grant_snapshot_bypass_removed',source_ref=raw['source_ref'],raw_copies=rawcount,pass_check=True))
 assert all(c['pass_check'] for c in checks);dump('checks/INDEPENDENT_RECOMPUTE.json',dict(checks=checks,passed=len(checks),failed=0,predictor_core_called=False,method='SQLite group counts; algebraic bounds vs finite completion enumeration'));dump('checks/MONOTONICITY.json',dict(violations=monotonic,profiles_checked=10,queries_per_profile=19392));assert not monotonic;dump('IDENTIFIABILITY_WITNESSES.json',witness)
 print(canonical({'independent_checks':len(checks),'monotonicity_violations':len(monotonic),'actual_finite_witness_pairs':len(witness),'raw_grant_snapshot_copies_tested':rawcount}))
if __name__=='__main__':main()
