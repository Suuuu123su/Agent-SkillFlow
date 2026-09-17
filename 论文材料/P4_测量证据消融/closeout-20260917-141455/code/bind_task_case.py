from common import *
guard();data=read(OUT/'data/closeout_data.json');ids={data['cases']['selected_predictions'][data['cases']['task']['query_id']]['V00']['registry']['independence_group']};found=[]
with (P4/'minimal_data/BASE_DOCUMENTS.jsonl').open(encoding='utf-8-sig') as f:
 for line,text in enumerate(f,1):
  d=json.loads(text)
  if d['id'] in ids:
   found.append({'unit':d['id'],'observation':d['observation'],'lifecycle':d['lifecycle'],'certificate':d['task_success_evidence'],'source_ref':(P4/'minimal_data/BASE_DOCUMENTS.jsonl').relative_to(ROOT).as_posix()+f'#L{line}','sha256':sha(P4/'minimal_data/BASE_DOCUMENTS.jsonl')});break
assert len(found)==1;dump('data/case_evidence_bindings.json',found)
man=read(OUT/'SOURCE_MANIFEST.json');p=P4/'minimal_data/BASE_DOCUMENTS.jsonl';man['sources'].append({'path':p.relative_to(ROOT).as_posix(),'absolute_path':str(p),'sha256':sha(p),'bytes':p.stat().st_size,'role':'single saved task certificate case evidence binding; no metrics recomputed'});dump('SOURCE_MANIFEST.json',man)
print(can({'task_query':data['cases']['task']['query_id'],'unit':found[0]['unit'],'obligations':found[0]['observation']['task_obligations'],'certificate_bindings':found[0]['certificate']}))
