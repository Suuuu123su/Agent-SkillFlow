from common import *
x=rows(P3/'facts/CORE_PROJECTIONS.jsonl')[0];print('task evidence',json.dumps(x['proof']['task'],ensure_ascii=False)[:8500]);print('raw task files',[k for k in table('f','core-trials')[0][0]['raw_files'] if 'task' in k or 'proof' in k])
