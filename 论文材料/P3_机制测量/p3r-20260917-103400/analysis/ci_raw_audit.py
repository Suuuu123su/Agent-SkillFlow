from common import *
from collections import Counter
offline_guard();out=[];unique={}
for phase in ['f','g','h']:
 mf=read(ROOT/f'datasets/t17-v2/stages/{phase}/dataset-manifest.json');base=ROOT/mf['stages'][0]['raw_relative_path'];cores={c['run_id']:c for c,_ in table(phase,'core-trials')}
 for r,ref in table(phase,'replay-pairs'):
  p=r['proof']
  if not p:continue
  m=p['manifest'];row={'phase':phase,'pair_id':r['identity']['unit_id'],'ref':ref,'checkpoint_hash':m['checkpoint_state_hash'],'prefix_hash':m['checkpoint_prefix_hash'],'ci':p['ci'],'target_alias':r['target_alias']}
  for arm,side in [('original','o'),('neutral','n')]:
   it=m[arm+'_intervention'];found=[]
   for rel,info in {**cores[r['source_core_run_id']]['raw_files'],**r['raw_files']}.items():
    if '/blobs/' not in rel or info['sha256']!=it['content_hash']:continue
    path=next((x for x in [base/rel,base.parent/'segment'/rel,base.parent/'raw'/rel,base.parent.parent/'attempt-01/raw'/rel] if x.is_file()),None)
    if path and sha(path)==info['sha256']:
     content=path.read_bytes();found.append({'ref':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'bytes':len(content),'text':content.decode('utf-8',errors='replace')})
   row[arm]=found[0] if found else None
  row['semantic_status']='whole_object_neutralization_only; business/schema preservation not independently assumed'
  row['raw_objects_present']=row['original'] is not None and row['neutral'] is not None
  row['structural_controls']=all(m['controls'][k] for k in ['same_other_inputs','same_permissions','same_seed','same_time','same_tool_returns','same_tool_set']) and len({m['checkpoint_state_hash'],m['original_restore_state_hash'],m['neutral_restore_state_hash']})==1 and len({m['checkpoint_prefix_hash'],m['original_prefix_hash'],m['neutral_prefix_hash']})==1
  if row['raw_objects_present']:
   key=(r['target_alias'],row['original']['text'],row['neutral']['text']);unique[key]=unique.get(key,0)+1
  out.append(row)
jl('evidence/CI_RAW_INTERVENTION_OBJECTS.jsonl',out);dump('audit/CI_RAW_INTERVENTION_CHECK.json',{'pairs':len(out),'raw_objects_present':sum(x['raw_objects_present'] for x in out),'structural_controls_pass':sum(x['structural_controls'] for x in out),'unique_text_pairs':[dict(target=k[0],original=k[1],neutral=k[2],count=v) for k,v in unique.items()]})
print('CI raw coverage',len(out),sum(x['raw_objects_present'] for x in out));print('Unique changes',json.dumps([dict(target=k[0],original=k[1],neutral=k[2],count=v) for k,v in unique.items()],ensure_ascii=False)[:7000])
