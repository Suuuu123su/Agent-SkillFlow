from common import *
import shutil

offline_guard();sources={}
def register(path,h=None,role='source'):
 p=Path(path);p=p if p.is_absolute() else ROOT/p
 if not p.is_file() or p.name in ['auth.json','.env'] or p.suffix=='.dpapi':return
 # Only declared project sources; never crawl outside the repository.
 if not p.resolve().is_relative_to(ROOT):return
 rel=p.relative_to(ROOT).as_posix();actual=sha(p);sources[rel]={'path':rel,'sha256':actual,'expected_sha256':h,'matches_expected':actual==h if h else None,'bytes':p.stat().st_size,'role':role}
old=read(OUT/'legacy/SOURCE_MANIFEST.json')
for x in old['sources']:register(x['path'],x.get('sha256'),'historical_P3_bound_source')
for x in rows(OUT/'evidence/ALR_ORIGINAL_DATABASE_LOOKUP.jsonl'):
 for r in x['raw']:register(r['path'],r['sha256'],'original_authorization_database')
for x in rows(OUT/'evidence/CI_RAW_INTERVENTION_OBJECTS.jsonl'):
 for arm in ['original','neutral']:
  if x[arm]:register(x[arm]['ref'],x[arm]['sha256'],'CI_original_intervention_bytes')
for x in csv.DictReader((OUT/'T18_ALR_RIR_RECOVERED.csv').open(encoding='utf-8-sig')):register(x['source'],x['sha256'],'T18_actual_construct_core')
def recursive(x,role):
 if isinstance(x,list):
  for v in x:recursive(v,role)
 elif isinstance(x,dict):
  for pkey in ['path','ref','source_path','raw_path']:
   if isinstance(x.get(pkey),str) and x.get('sha256'):register(x[pkey],x['sha256'],role)
  for v in x.values():
   if isinstance(v,(dict,list)):recursive(v,role)
for f in ['evidence/M2_SAFE_REQUEST_RESPONSE.jsonl','audit/MANIFEST_SOURCE_HASHES.json']:
 x=rows(OUT/f) if f.endswith('jsonl') else read(OUT/f);recursive(x,'original_M2_or_manifest')
for x in csv.DictReader((OUT/'M2_FIRST_FAILURES.csv').open(encoding='utf-8-sig')):
 for k,v in x.items():
  if v.startswith('runs/') and '#' not in v:register(v,None,'original_M2_request_response')
for p in PACK.rglob('*'):
 if p.is_file():register(p,None,'task_pack_data_not_executed')
dump('SOURCE_MANIFEST_P3R.json',{'repository_root':str(ROOT),'local_head':old['local_head'],'sources':list(sources.values()),'source_count':len(sources),'hash_mismatches':[x for x in sources.values() if x['matches_expected'] is False],'legacy_complete_index':'legacy/SOURCE_MANIFEST.json','new_output_hash_index':'BUNDLE_MANIFEST.json','raw_authentication_files_read':False,'independent_freeze_limit':'Historical exact manifest bytes and service-side model snapshot remain unproven'})
baseline=read(OUT/'audit/BASELINE_HASHES.json');checks=[]
for p,h in baseline.items():
 file=Path(p);now=sha(file) if file.is_file() else None;checks.append(dict(path=p,expected=h,current=now,unchanged=now==h))
dump('audit/HISTORICAL_PRESERVATION.json',{'checked':len(checks),'changed':[x for x in checks if not x['unchanged']],'all_unchanged':all(x['unchanged'] for x in checks),'checks':checks})
for f in ['HIAA_POTENTIAL_SETS.json','CI_IDENTITY_SENSITIVITY.csv','ALR_STRICT_CONTRACT.csv']:
 if (OLD/'tables'/f).exists() and not (OUT/'legacy'/f).exists():shutil.copyfile(OLD/'tables'/f,OUT/'legacy'/f)
print(json.dumps({'source_count':len(sources),'source_mismatches':sum(x['matches_expected'] is False for x in sources.values()),'baseline_files':len(checks),'baseline_changed':sum(not x['unchanged'] for x in checks)}))
