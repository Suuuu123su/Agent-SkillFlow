"""Post-prediction aggregation/evaluation; this module never imports the predictor."""
from common import *
from collections import Counter,defaultdict
from views import renamed

def valkey(x):return canonical(x)
def main():
 guard();reg={r['query_id']:r for r in rows(OUT/'QUERY_REGISTRY.jsonl')};gold={g['query_id']:g for g in rows(OUT/'GOLD_PROVENANCE.jsonl')};pref={g['query_id']:g for g in rows(OUT/'control/PROVENANCE_REFERENCE.jsonl')};slots=read(OUT/'control/SAVED_LIVE_SLOT_METADATA.json');dump('control/SAVED_LIVE_SLOT_METADATA.json',slots)
 docs=rows(OUT/'minimal_data/BASE_DOCUMENTS.jsonl');strings=set()
 def walk(x):
  if isinstance(x,str):strings.add(x)
  elif isinstance(x,dict):
   for k,v in x.items():strings.add(k);walk(v)
  elif isinstance(x,list):
   for v in x:walk(v)
 walk(docs);inverse={renamed(v):v for v in strings if renamed(v)!=v};assert len(inverse)==sum(renamed(v)!=v for v in strings)
 base={r['query_id']:r for r in rows(OUT/'results/V00.jsonl')};summaries=[];transitions=[];scores=[];wrong=[];controls=[];provsum=[];hcell=[];hsummary=[];alr=[];rir=[];ci=[];read_audit=[];alllong=[]
 for i in range(13):
  vid=f'V{i:02}';results=rows(OUT/f'results/{vid}.jsonl');assert len(results)==len(reg);assert {r['query_id'] for r in results}==set(reg);groups=defaultdict(list);trans=Counter();sc=defaultdict(Counter);ps=defaultdict(Counter);negative_diff=[]
  aud=read(OUT/f'audit/full-{vid}.json');assert not aud['errors'];read_audit.append(dict(view_id=vid,**aud))
  for line,p in enumerate(results,1):
   r=reg[p['query_id']];slot=slots.get(r['native_unit_ref'],{});variant=slot.get('source_variant','');branch=slot.get('branch','');row=dict(view_id=vid,**r,source_variant=variant,branch=branch,eligibility=p['eligibility'],status=p['status'],value=p['value'],lower=p['lower'],upper=p['upper'],reason=p['reason'],result_ref=f'results/{vid}.jsonl#L{line}',used_evidence_count=len(p['used_evidence']),missing_evidence_count=len(p['missing_evidence']));alllong.append(row)
   key=(r['domain'],r['study'],r['phase'],r['metric'],r['protocol'],r['horizon'],variant,branch);groups[key].append(p);b=base[p['query_id']];tk=(r['domain'],r['metric'],r['protocol'],str(r['horizon']),b['status'],str(b['eligibility']),p['status'],str(p['eligibility']));trans[tk]+=1
   if vid in ['V11','V12']:
    v=p['value'];v=sorted(inverse.get(x,x) for x in v) if vid=='V12' and isinstance(v,list) else v
    if [p['status'],p['eligibility'],v,p['lower'],p['upper']]!=[b['status'],b['eligibility'],b['value'],b['lower'],b['upper']]:negative_diff.append(p['query_id'])
   if p['query_id'] in gold:
    g=gold[p['query_id']];skey=(g['domain'],r['metric'],r['protocol']);z=sc[skey];z['reference_queries']+=1
    if g['truth_available']:
     z['truth_available']+=1
     if p['status']=='point':
      z['determinate']+=1
      if p['value']==g['value'] and p['eligibility'] is True:z['correct']+=1
      else:z['wrong_determinate']+=1;wrong.append(dict(view=vid,query_id=p['query_id'],kind='value',prediction=p['value'],truth=g['value']))
     if p['lower'] is not None and isinstance(g['value'],(int,float)):
      z['bound_checked']+=1
      if not p['lower']<=g['value']<=p['upper']:z['bound_excludes_truth']+=1;wrong.append(dict(view=vid,query_id=p['query_id'],kind='bound'))
    if g['eligibility_known']:
     z['eligibility_known']+=1
     if p['eligibility'] is not None:
      z['eligibility_determined']+=1
      if p['eligibility']!=g['eligibility']:z['wrong_eligibility']+=1;wrong.append(dict(view=vid,query_id=p['query_id'],kind='eligibility'))
   if r['metric']=='Provenance' and p['query_id'] in pref:
    z=ps[(r['domain'],r['phase'])];z['fixed_artifacts']+=1
    if p['status']=='point':
     observed=set(inverse.get(v,v) for v in p['value']) if vid=='V12' else set(p['value']);expected=set(pref[p['query_id']]['reference_origins']);z['known_artifacts']+=1;z['tp']+=len(observed&expected);z['fp']+=len(observed-expected);z['fn']+=len(expected-observed)
    else:z['unknown_artifacts']+=1
   loc=dict(view_id=vid,query_id=p['query_id'],domain=r['domain'],phase=r['phase'],native_unit_ref=r['native_unit_ref'],protocol=r['protocol'],horizon=r['horizon'],source_variant=variant,source_ref=r['source_ref'],result_ref=row['result_ref'],eligibility=p['eligibility'],status=p['status'],value=p['value'],lower=p['lower'],upper=p['upper'])
   if r['metric']=='HIAA_run':
    hsummary.append({**loc,**p['details']})
    for cell,c in p['details']['cells'].items():hcell.append({**loc,'cell':cell,**c})
   if r['metric']=='ALR':alr.append({**loc,'request_id':r['parameters'].get('op'),**p['details']})
   if r['metric']=='RIR':rir.append({**loc,**p['details']})
   if r['metric']=='CI':ci.append({**loc,**p['details']})
  for key,rr in groups.items():
   domain,study,phase,metric,protocol,k,variant,branch=key;n=len(rr);eligible=[p for p in rr if p['eligibility'] is True];knownnum=[p for p in eligible if p['status']=='point' and isinstance(p['value'],(int,float))];isbool=metric in ['ALR','RIR','UEA','TaskSuccess','E_STS','HIAA_Y'];ntrue=sum(p['value'] is True for p in eligible if p['status']=='point');nfalse=sum(p['value'] is False for p in eligible if p['status']=='point');den=len(eligible);nu=den-ntrue-nfalse
   summaries.append(dict(view_id=vid,domain=domain,study=study,phase=phase,metric=metric,protocol=protocol,horizon=k,source_variant=variant,branch=branch,fixed_queries=n,eligible_true=den,eligible_false=sum(p['eligibility'] is False for p in rr),eligible_unknown=sum(p['eligibility'] is None for p in rr),**{st:sum(p['status']==st for p in rr) for st in ['point','bounded','unknown','not_applicable','conflict','analysis_error']},point_identifiability=sum(p['status']=='point' for p in rr)/n,positive=ntrue if isbool else None,negative=nfalse if isbool else None,unknown_in_eligible=nu if isbool else None,rate_lower=ntrue/den if den and isbool else None,rate_upper=(ntrue+nu)/den if den and isbool else None,numeric_sum=sum(p['value'] for p in knownnum) if knownnum else None,numeric_point_n=len(knownnum),unknown_reasons=dict(Counter(p['reason'] or 'no_extra_reason' for p in rr if p['status'] in ['unknown','bounded']))))
  for key,c in trans.items():transitions.append(dict(view_id=vid,domain=key[0],metric=key[1],protocol=key[2],horizon=key[3],full_status=key[4],full_eligibility=key[5],view_status=key[6],view_eligibility=key[7],queries=c))
  for key,z in sc.items():scores.append(dict(view_id=vid,domain=key[0],metric=key[1],protocol=key[2],**dict(z),judgment_coverage=z['determinate']/z['truth_available'] if z['truth_available'] else None,selective_accuracy=z['correct']/z['determinate'] if z['determinate'] else None))
  for key,z in ps.items():
   dn=2*z['tp']+z['fp']+z['fn'];provsum.append(dict(view_id=vid,domain=key[0],phase=key[1],**dict(z),f1_numerator=2*z['tp'] if z['known_artifacts'] else None,f1_denominator=dn if z['known_artifacts'] else None,f1=2*z['tp']/dn if dn else None,coverage=z['known_artifacts']/z['fixed_artifacts'],scope='recorded oracle member agreement, not live natural accuracy'))
  controls.append(dict(view_id=vid,queries=len(results),negative_control_differences=negative_diff if vid in ['V11','V12'] else None))
 csvout('ABLATION_LONG.csv',alllong);csvout('P4_METRIC_MAIN.csv',summaries);jl('P4_METRIC_MAIN.jsonl',summaries);csvout('ELIGIBILITY_UNKNOWN_TABLE.csv',summaries);csvout('FULL_TO_VIEW_TRANSITIONS.csv',transitions);csvout('INDEPENDENT_REFERENCE_SCORES.csv',scores);csvout('PROVENANCE_MICRO_F1.csv',provsum);csvout('HIAA_CELLS.csv',hcell);csvout('HIAA_CONTRASTS.csv',hsummary);csvout('ALR_REQUEST_FUNNEL.csv',alr);csvout('RIR_SESSION_COHORTS.csv',rir);csvout('CI_DETAILS.csv',ci);jl('READ_AUDIT.jsonl',read_audit);dump('checks/FULL_EVALUATION.json',dict(results=len(alllong),views=13,queries=19392,wrong_determinate=wrong,negative_controls=controls,full_is_gold=False,live_accuracy_claimed=False));assert not wrong;assert all(not x['negative_control_differences'] for x in controls)
 print(canonical({'results':len(alllong),'summary_rows':len(summaries),'wrong_determinate':len(wrong),'provenance_rows':len(provsum),'full_status_counts':dict(Counter(p['status'] for p in base.values()))}))
if __name__=='__main__':main()
