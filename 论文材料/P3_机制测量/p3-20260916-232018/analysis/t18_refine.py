"""T18-specific target binding and frozen matrix groups; targeted appendix refinement."""
import json,csv,ast,sys,os,hashlib,collections
from pathlib import Path
OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[2];READS=set();BINDINGS=[]
for node in ast.parse((OUT/'analysis/independent.py').read_text('utf-8-sig')).body:
 if isinstance(node,ast.FunctionDef) and node.name in ('guard','dump','jl','csvout','unique','selected'):exec(compile(ast.Module(body=[node],type_ignores=[]),'<parse>','exec'))
sys.addaudithook(guard)
rows=[json.loads(x) for x in (OUT/'facts/T18_RUNS.jsonl').open(encoding='utf-8')];lookup={(x['domain'],x['trial_id']):x for x in rows};cells=[];contrasts=[];checks=[]
for domain in ('scripted','fake_reference'):
 directory=ROOT/'datasets/t18-local'/domain;mf=json.loads((directory/'manifest.json').read_text('utf-8'));matrix=json.loads((directory/'matrix.json').read_text('utf-8'));pre=json.loads((directory/'preregistration.json').read_text('utf-8'));controls=pre['hiaa_controls'][domain]
 for n in mf['files']:
  if not n.startswith('cores/'):continue
  c=json.loads((directory/n).read_text('utf-8'));d=c['data'];r=lookup[(domain,c['cell']['trial_id'])];risk={e['effect_id'] for s in d['task_contract']['risk_selectors'] for e in selected(d['facts'],s)};r.update(harm_y=bool(risk),risk_effect_ids=sorted(risk),selector_basis='T18 task_contract.risk_selectors; metadata.harm_selector is absent',behavior_valid=c['status']=='completed' and not any(x['behavior'] in ('refusal','no_call','schema_rejection') for x in c['decisions']))
  saved=d['proof'];checks.append({'domain':domain,'run_id':c['run_id'],'task_match':r['task_success']==saved['task']['task_success'],'safe_task_match':r['safe_task_success']==saved['task']['safe_task_success'],'uea_match':r['uea']==saved['report']['uea']['uea_count'],'target_match':set(saved['task']['risk_effect_ids'])==risk})
 for g in matrix['hiaa_groups']:
  hashes={x['shared_contract_sha256'] for x in controls if x['design_id']==g['design_id']};assert len(hashes)==1
  for label,trial in g['cells'].items():
   r=lookup[(domain,trial)];cells.append({'domain':domain,'design':g['design_id'],'base':g['base_id'],'mode':g['mode'],'cell':label,'trial_id':trial,'run_id':r['run_id'],'numerator':int(r['harm_y']),'denominator':1,'unknown':0,'behavior_valid':r['behavior_valid'],'shared_contract_sha256':next(iter(hashes)),'source_ref':r['source_ref'],'risk_effect_ids':r['risk_effect_ids']})
  cs={x['cell']:x for x in cells if x['domain']==domain and x['design']==g['design_id']};value=sum(sign*cs[cell]['numerator'] for cell,sign in [('p00',1),('p01',-1),('p10',-1),('p11',1)])
  contrasts.append({'domain':domain,'design':g['design_id'],'mode':g['mode'],'HIAA_scheduled':value,'cells':{k:cs[k]['numerator'] for k in cs},'complete_four_cell':True,'shared_contract_match':True,'inference':'one frozen local quartet; no live frequency or population CI'})
strata=[]
for key in sorted({(x['domain'],x['split'],x['mode']) for x in rows}):
 ss=[x for x in rows if (x['domain'],x['split'],x['mode'])==key];strata.append({'domain':key[0],'split':key[1],'mode':key[2],'cores':len(ss),'task_success':sum(x['task_success'] for x in ss),'safe_task_success':sum(x['safe_task_success'] for x in ss),'uea':sum(x['uea'] for x in ss)})
jl('facts/T18_RUNS.jsonl',rows);csvout('tables/T18_HIAA_CELLS.csv',cells);csvout('tables/T18_HIAA_CONTRASTS.csv',contrasts);csvout('tables/T18_STRATA.csv',strata);dump('audit/T18_RAW_ENDPOINT_CHECKS.json',checks)
assert all(all(x[k] for k in ('task_match','safe_task_match','uea_match','target_match')) for x in checks)
dump('audit/T18_TARGET_BINDING_REFINEMENT.json',{'reason':'initial generic metadata selector is absent in T18; use frozen T18 report_data.hiaa_trials task risk selector; initial placeholder false coercion not retained as result','core_endpoint_checks':len(checks),'all_match':True,'group_count':len(contrasts),'new_calls':0})
print('T18 verified',len(checks),'cores;',len(contrasts),'frozen four-cell groups')
