from common import *
from views import project,PROFILES
from collections import Counter

guard();docs=rows(OUT/'minimal_data/BASE_DOCUMENTS.jsonl');queries=rows(OUT/'minimal_data/PREDICTOR_QUERIES.jsonl');reg={r['query_id']:r for r in rows(OUT/'QUERY_REGISTRY.jsonl')}
# Admission uses preexisting controlled cases plus all grid contracts and deterministic first legacy probes.
selected=[];counts=Counter();byid={d['id']:d for d in docs}
for q in queries:
 r=reg[q['query_id']];key=(r['domain'],r['metric'],r['protocol'],r['phase'])
 actual_sensitive=q['metric']=='ALR' and q.get('op') and bool(byid[q['unit']].get('provenance',{}).get('claim_objects',[]))
 if actual_sensitive or r['domain'] in ['CONTROLLED_CONSTRUCT','FINITE_CONSTRUCT'] or q['metric']=='HIAA_run' or (counts[key]<1 and r['domain'] in ['HISTORICAL_LIVE','T18_SCRIPTED','SAVED_LIVE']):selected.append(q);counts[key]+=1
manifests=[]
for vid in PROFILES:
 d=OUT/'views/admission'/vid;d.mkdir(parents=True,exist_ok=True);pdocs=[project(x,vid) for x in docs];qs=[]
 for q in selected:
  x=project(q,vid);x['query_id']=q['query_id'];qs.append(x)
 jl(d.relative_to(OUT)/'DOCUMENTS.jsonl',pdocs);jl(d.relative_to(OUT)/'QUERIES.jsonl',qs);manifests.append(dict(view_id=vid,documents_sha256=sha(d/'DOCUMENTS.jsonl'),query_sha256=sha(d/'QUERIES.jsonl'),query_count=len(qs),source_base_sha256=sha(OUT/'minimal_data/BASE_DOCUMENTS.jsonl'),hash_scope='new projection, not original signature'))
jl('checks/ADMISSION_VIEW_MANIFESTS.jsonl',manifests);dump('checks/ADMISSION_SELECTION.json',{'queries':[q['query_id'] for q in selected],'count':len(selected),'selection':'all existing controlled constructs; six grids both policies; first fixed probe per historical family; no prediction inspected'});print('Admission queries',len(selected),'x',len(PROFILES))
