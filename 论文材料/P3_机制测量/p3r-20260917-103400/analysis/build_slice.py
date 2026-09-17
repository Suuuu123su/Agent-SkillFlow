from common import *
import shutil
offline_guard();S=OUT/'review_slice';S.mkdir(exist_ok=True);index={'execution_domain':'SCRIPTED_NEW plus one saved LIVE_LEGACY CI example','units':{},'rir':[],'alr':[],'hashes':{}}
construct=read(OUT/'construct/CONSTRUCT_RESULTS.json')
for row in construct:
 label=row['case'];module=row['module'];paths=row['paths'];selected=list(paths)
 for branch in selected:
  src=OUT/paths[branch];state=read(src/'state.json');unit=state['events'][-1]['unit'];rel='units/'+src.name
  if not (S/rel).exists():shutil.copytree(src,S/rel)
  index['units'][unit]=rel
 # Include true producer prefix files because cloned state refers to its historical receipts.
 prefix_name=(label+'-prefix') if module=='RIR' else (label+'-alr-prefix');prefix=OUT/'construct/execution-v1'/prefix_name;prefix_unit=read(prefix/'state.json')['events'][-1]['unit'];prel='units/'+prefix_name
 if not (S/prel).exists():shutil.copytree(prefix,S/prel)
 index['units'][prefix_unit]=prel
 units={a:read(OUT/paths[a]/'state.json')['events'][-1]['unit'] for a in paths}
 if module=='RIR':index['rir'].append(dict(case=label,**units,prefix=prefix_unit,expected={'positive':'confirmed','negative':'confirmed_no_residual','legal_retention':'revocation_absent','missing_memory':'memory_unformed'}[label]))
 else:index['alr'].append(dict(case=label,**units,prefix=prefix_unit,expected=True if label=='positive' else None if label=='unknown_reason' else False))
(S/'observations').mkdir(exist_ok=True)
shutil.copyfile(OUT/'construct/unknown_reason_observation.json',S/'observations/missing_reason.json')
for item in index['alr']:
 if item['case']=='unknown_reason':item['measurement_view']='observations/missing_reason.json'
shutil.copyfile(OUT/'POT_SETS_AND_WITNESSES.json',S/'pot.json')
unstable=next(x for x in csv.DictReader((OLD/'tables/CI_PAIRS.csv').open(encoding='utf-8-sig')) if x['phase']=='f' and x['identity_vs_core_stable']=='False');core=next(r for r,_ in table('f','core-trials') if r['run_id']==unstable['run_id']);rp=next(r for r,_ in table('f','replay-pairs') if r['identity']['unit_id']==unstable['unit_id']);(S/'ci_unstable.json').write_text(json.dumps({'core':core,'replay':rp,'expected':unstable},ensure_ascii=False),encoding='utf-8')
v=read(OLD/'facts/FRESH_VECTORS.json')['g'];(S/'statistics.json').write_text(json.dumps({k:v[k] for k in ['hiaa.c1-context-grid.scheduled','hiaa.c2-tool-return-grid.scheduled']},ensure_ascii=False),encoding='utf-8')
shutil.copyfile(OUT/'analysis/portable_verify_template.py',S/'recompute.py')
for p in S.rglob('*'):
 if p.is_file() and p.name not in ['index.json','RECOMPUTED.json']:index['hashes'][p.relative_to(S).as_posix()]=sha(p)
(S/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf-8')
print('Slice',len(index['units']),'actual tool-execution units, files',len(index['hashes']))
