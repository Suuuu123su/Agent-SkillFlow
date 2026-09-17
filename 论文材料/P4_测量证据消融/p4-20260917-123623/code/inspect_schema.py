from common import *
guard()
c=next(c for c,_ in table('f','core-trials') if c['identity']['condition_id']=='a1-implicit-text');d=c['data'];f=d['facts'];print('DATA_KEYS',list(d));print('IDENTITY',c['identity']);print('DEFINITION',json.dumps(d['analysis_definition'],ensure_ascii=False)[:12000]);print('FACT_KEYS',list(f))
for name in ['events','effects','receipts','grants','revocations','artifacts','decisions']:
 print(name,json.dumps(f.get(name,[])[:2],ensure_ascii=False)[:3200])
print('PROOF_TASK',json.dumps(d.get('proof',{}).get('task'),ensure_ascii=False));print('CORE_DECISIONS',json.dumps(c['decisions'][:1],ensure_ascii=False));r=next(x for x,_ in table('f','replay-pairs') if x['source_core_run_id']==c['run_id']);print('REPLAY_PROOF_KEYS',list(r['proof']));print('REPLAY_MANIFEST',json.dumps(r['proof']['manifest'],ensure_ascii=False)[:6500]);print('task pack files',read(PACK/'MANIFEST.json')['files'][:1] if isinstance(read(PACK/'MANIFEST.json')['files'],list) else list(read(PACK/'MANIFEST.json')['files'])[:1])
