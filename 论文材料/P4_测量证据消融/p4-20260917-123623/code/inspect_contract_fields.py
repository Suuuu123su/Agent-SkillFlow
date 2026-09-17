from common import *
guard()
for p,cond in [('f','a1-implicit-text'),('f','m2-target-revoked'),('g','m2-target-revoked')]:
 c=next(c for c,_ in table(p,'core-trials') if c['identity']['condition_id']==cond);d=c['data'];print(p,cond)
 for k in ['task_contract','observed','claim_bindings','metadata']:print(k,json.dumps(d[k],ensure_ascii=False)[:6500])
 print('oracle',json.dumps(d['oracle'][:2],ensure_ascii=False)[:1800])
 print('revokes',json.dumps(d['facts']['revocations'],ensure_ascii=False))
 print('fail',c['issues'][:1],c['reason'],c['status'])
