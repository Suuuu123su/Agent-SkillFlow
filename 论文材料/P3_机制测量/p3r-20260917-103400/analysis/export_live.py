"""Public projection of actual synthetic model turns. Never exports auth, SSE or reasoning."""
from common import *
from collections import Counter

offline_guard();L=OUT/'live';attempts=rows(L/'raw/attempts.jsonl');results=rows(L/'raw/results.jsonl')
def clean(x):
 if isinstance(x,list):return [clean(v) for v in x if not(isinstance(v,dict) and v.get('type')=='reasoning')]
 if isinstance(x,dict):return {k:clean(v) for k,v in x.items() if k not in {'encrypted_content','reasoning_content','safety_identifier','prompt_cache_key','client_metadata','user','authorization','access_token','refresh_token','id_token'} and not(k=='reasoning' and isinstance(v,(str,list)))}
 return x
A=[];R=[]
for x in attempts:
 q=clean(x);q['projection']='actual forwarded request; runtime identifiers removed; original hash retained';A.append(q)
for x in results:
 q={k:v for k,v in x.items() if k!='response'};response=x.get('response')
 q['response']=None if response is None else clean({k:v for k,v in response.items() if k in ['id','model','status','created_at','completed_at','incomplete_details','error','usage','output']});q['projection']='actual response visible output and usage only; private reasoning omitted';R.append(q)
jl('live/public/REQUESTS.jsonl',A);jl('live/public/RESULTS.jsonl',R)
ids=[x['id'] for x in A];rids=[x['id'] for x in R];by={x['id']:x for x in R};index=[]
for x in A:
 y=by.get(x['id']);index.append(dict(request_id=x['id'],unit=x['unit'],role=x['role'],endpoint=x['endpoint'],request_sha256=x['request_sha256'],status='IN_FLIGHT' if y is None else 'UNKNOWN' if y.get('unknown_delivery') else (y.get('response') or {}).get('status') or 'NO_RESPONSE',failure=None if y is None else y.get('failure'),http_status=None if y is None else y.get('http_status'),response_id=None if y is None else (y.get('response') or {}).get('id'),model=None if y is None else (y.get('response') or {}).get('model'),actual_tokens=None if y is None else (y.get('response') or {}).get('usage'),request_line=ids.index(x['id'])+1,result_line=rids.index(x['id'])+1 if x['id'] in rids else None))
csvout('live/public/ATTEMPT_RESULT_INDEX.csv',index)
freeze=read(L/'FORMAL_CODE_FREEZE.json');freeze_checks=[dict(path=p,expected=h,current=sha(OUT/p),match=sha(OUT/p)==h) for p,h in freeze.items()]
slots=list(csv.DictReader((PACK/'capacity_slots.csv').open(encoding='utf-8-sig')));slotby={x['slot_id']:x for x in slots};unitcounts=Counter(x['unit'] for x in A);ledger=read(L/'ledger.json');limits=[]
for unit,s in slotby.items():
 # CSV cap is authoritative; inspect keys instead of recomputing total budget.
 cap=int(s['max_requests']);limits.append(dict(unit=unit,actual_requests=unitcounts[unit],cap=cap,within_cap=unitcounts[unit]<=cap,status=ledger['units'][unit]['status'],execution_disposition='NOT_ENABLED_RESERVED_UNUSED' if unit in ['TECH-03','TECH-04'] and not unitcounts[unit] else ledger['units'][unit]['status']))
csvout('live/public/SLOT_CAP_AUDIT.csv',limits)
summary={'attempts':len(A),'results':len(R),'unique_attempt_ids':len(set(ids)),'duplicate_attempt_ids':len(ids)-len(set(ids)),'duplicate_result_ids':len(rids)-len(set(rids)),'unmatched_results':sorted(set(rids)-set(ids)),'pending_results':sorted(set(ids)-set(rids)),'by_unit':dict(unitcounts),'role_counts':dict(Counter(x['role'] for x in A)),'models':dict(Counter(x['request']['model'] for x in A)),'actual_response_models':dict(Counter((x.get('response') or {}).get('model') for x in R)),'endpoints':dict(Counter(x['endpoint'] for x in A)),'slot_cap_failures':[x for x in limits if not x['within_cap']],'frozen_source_checks':freeze_checks,'frozen_source_failures':[x for x in freeze_checks if not x['match']],'automatic_resubmission':False,'sanitization':'Private auth/home, raw SSE and reasoning absent. Exact forwarded requests are hashed locally; public projection removes runtime account/cache identifiers only.'}
dump('live/public/EXECUTION_AUDIT.json',summary)
print(json.dumps({k:v for k,v in summary.items() if k not in ['by_unit','frozen_source_checks']},ensure_ascii=False))

