from common import *
from collections import Counter
for f in ['ALR_STRICT_FUNNEL.csv','RIR_LEGACY_AND_CHAIN.csv','CI_FULL_AND_STABILITY.csv','T18_ALR_RIR_RECOVERED.csv','legacy/HIAA_CELLS.csv','legacy/HIAA_CONTRASTS.csv']:
 r=list(csv.DictReader((OUT/f).open(encoding='utf-8-sig')));print(f,len(r),json.dumps(r[:1],ensure_ascii=False)[:2100])
for f in ['live/ledger.json','POT_SETS_AND_WITNESSES.json','construct/CONSTRUCT_RESULTS.json','live/raw/attempts.jsonl','live/raw/results.jsonl']:
 x=rows(OUT/f)[0] if f.endswith('jsonl') else read(OUT/f);print(f,'keys',list(x) if isinstance(x,dict) else 'list '+str(len(x)))
 if f.endswith('attempts.jsonl'): print({k:(list(v) if isinstance(v,dict) else type(v).__name__) for k,v in x.items()})
 if f.endswith('results.jsonl'):print({k:(list(v) if isinstance(v,dict) else type(v).__name__) for k,v in x.items()})
 if f.endswith('ledger.json'):print(x['requests'],dict(Counter(v['status'] for v in x['units'].values())))
r=list(csv.DictReader((OUT/'legacy/METRICS_LONG.csv').open(encoding='utf-8-sig')))
print('legacy',len(r));print([(x['phase'],x['metric_id'],x['value'],x['numerator'],x['denominator']) for x in r if x['phase'] in ['f','g','h']])
