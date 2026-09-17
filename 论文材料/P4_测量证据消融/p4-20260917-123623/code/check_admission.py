from common import *
from views import PROFILES,renamed
from collections import Counter

def semantics(r,inverse=None):
 v=r['value']
 if isinstance(v,list) and inverse:v=sorted(inverse.get(x,x) for x in v)
 return [r['eligibility'],r['status'],v,r['lower'],r['upper']]
def main():
 guard();gold={x['query_id']:x for x in rows(OUT/'GOLD_PROVENANCE.jsonl')};docs=rows(OUT/'minimal_data/BASE_DOCUMENTS.jsonl');strings=set()
 def walk(x):
  if isinstance(x,str):strings.add(x)
  elif isinstance(x,list):
   for v in x:walk(v)
  elif isinstance(x,dict):
   for k,v in x.items():strings.add(k);walk(v)
 walk(docs);inverse={renamed(s):s for s in strings if renamed(s)!=s};base={x['query_id']:x for x in rows(OUT/'checks/admission-V00-r0.jsonl')};errors=[];counts=[]
 for vid in PROFILES:
  rr=rows(OUT/f'checks/admission-{vid}-r0.jsonl');correct=judged=truthn=0;bounds=0
  for p in rr:
   g=gold.get(p['query_id'])
   if p['status']=='analysis_error':errors.append([vid,p['query_id'],'analysis_error'])
   if vid in ['V11','V12'] and semantics(p,inverse if vid=='V12' else None)!=semantics(base[p['query_id']]):errors.append([vid,p['query_id'],'negative_control_changed'])
   if not g:continue
   if g['truth_available']:
    truthn+=1
    if p['status']=='point':
     judged+=1
     if p['value']==g['value'] and p['eligibility'] is True:correct+=1
     else:errors.append([vid,p['query_id'],'wrong_determinate_value',p['value'],g['value']])
    if p['lower'] is not None and isinstance(g['value'],(int,float)):
     bounds+=1
     if not p['lower']<=g['value']<=p['upper']:errors.append([vid,p['query_id'],'excluded_truth'])
   if g['eligibility_known'] and p['eligibility'] is not None and p['eligibility']!=g['eligibility']:errors.append([vid,p['query_id'],'wrong_eligibility',p['eligibility'],g['eligibility']])
  aud=read(OUT/f'audit/admission-{vid}-r0.json');assert aud['blocked_accesses'] and not aud['errors'];assert not any(x['path'].endswith('REFERENCE_INPUTS.jsonl') for x in aud['file_accesses']);counts.append(dict(view=vid,queries=len(rr),reference_truths=truthn,point_judged=judged,point_correct=correct,coverage=judged/truthn if truthn else None,selective_accuracy=correct/judged if judged else None,bounds_checked=bounds))
 csvout('checks/ADMISSION_REFERENCE.csv',counts);dump('checks/ADMISSION_REVIEW.json',dict(errors=errors,queries_per_view=len(base),view_count=13,negative_controls='pass' if not any('negative_control_changed' in x for x in errors) else 'fail',status='PASS' if not errors else 'FAIL'))
 print(canonical({'errors':errors[:20],'error_count':len(errors),'reference':counts}))
if __name__=='__main__':main()
