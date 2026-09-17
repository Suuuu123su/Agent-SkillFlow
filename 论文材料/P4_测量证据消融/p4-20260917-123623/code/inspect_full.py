from common import *
from collections import Counter,defaultdict
reg={r['query_id']:r for r in rows(OUT/'QUERY_REGISTRY.jsonl')}
ss=rows(OUT/'P4_METRIC_MAIN.jsonl')
for vid in ['V00','V01','V02','V03','V04','V05','V06','V07','V08','V09','V10','V11','V12']:
 r=[x for x in ss if x['view_id']==vid];print(vid,{k:sum(x[k] for x in r) for k in ['point','bounded','unknown','not_applicable','eligible_unknown']})
for metric in ['HIAA_run','ALR','RIR','CI']:
 rr=[p for p in rows(OUT/'results/V00.jsonl') if p['metric']==metric];z=defaultdict(Counter)
 for p in rr:
  r=reg[p['query_id']];key=(r['domain'],r['phase'],r['protocol'],r['horizon'])
  if r['domain'] not in ['HISTORICAL_LIVE','SAVED_LIVE']:continue
  z[key][p['status']+':'+str(p['value'])]+=1
 print(metric,dict((str(k),dict(v)) for k,v in z.items()))
print('F1',[(r['phase'],r['tp'],r['fp'],r['fn'],r['f1']) for r in csv.DictReader((OUT/'PROVENANCE_MICRO_F1.csv').open(encoding='utf-8-sig')) if r['view_id']=='V00' and r['domain']=='HISTORICAL_LIVE'])
