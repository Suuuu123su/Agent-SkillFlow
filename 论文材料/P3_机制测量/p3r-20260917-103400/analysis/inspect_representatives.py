import json
from pathlib import Path
R=Path(r'E:\Skill ＆ Harness\Agent');p=R/'runs/t17-v2-deepseek-20260904-01/model2/attempt-02/segment'
us=[json.loads(l) for l in (p/'api-usage.jsonl').read_text().splitlines()]
for cid in ['call-3b88380120955b98','call-dbc2b3ffccccdca9']:
 a=next(x for x in us if (x.get('call') or {}).get('call_id')==cid and x['event_type']=='attempt');f=p/'api-private'/f"{a['attempt_index']:06}.json";d=json.loads(f.read_text()); req,res=d['request'],d['response'];print('FILE',f);print('REQUEST',json.dumps(req,ensure_ascii=False));print('RESPONSE SAFE',json.dumps({k:v for k,v in res.items() if k!='output'},ensure_ascii=False));print('VISIBLE OUTPUT',[x for x in res.get('output',[]) if x.get('type')!='reasoning']);print('output item types',[x.get('type') for x in res.get('output',[])])

