"""Package only explicitly public artifacts. Must run after final settlement."""
from common import *
import zipfile,re

offline_guard();status=read(OUT/'P3R_STATUS.json');assert status['execution_complete'],'Live still running; no final ZIP'
assert read(OUT/'audit/HISTORICAL_PRESERVATION.json')['all_unchanged']
execaudit=read(OUT/'live/public/EXECUTION_AUDIT.json');assert not execaudit['slot_cap_failures'] and not execaudit['frozen_source_failures'] and not execaudit['pending_results']
assert execaudit['duplicate_attempt_ids']==execaudit['duplicate_result_ids']==0
assert not read(OUT/'live/public/INDEPENDENT_VALIDATION.json')['failed'];assert read(OUT/'live/public/INDEPENDENT_METRICS.json')['failed']==0
roots=['analysis','audit','legacy','facts','evidence','construct','review_slice','task_pack','live/code','live/public','live/units'];files=[]
for p in OUT.iterdir():
 if p.is_file() and p.suffix in ['.md','.json','.jsonl','.csv','.html'] and p.name not in ['BUNDLE_MANIFEST.json','ZIP_RECEIPT.json','PACKAGE_VERIFICATION.json']:files.append(p)
for r in roots:
 for p in (OUT/r).rglob('*'):
  if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.pyc','.zip']:files.append(p)
for name in ['ledger.json','USER_AUTHORIZATION.json','TECH_VALIDATION.json','FORMAL_CODE_FREEZE.json','PREFLIGHT_CODE_FREEZE.json','CLI_OFFLINE_ADMISSION.json','batch_control.jsonl']:
 if (OUT/'live'/name).is_file():files.append(OUT/'live'/name)
for name in ['ISOLATION_POSITIVE_TEST.json','negative_isolation_result.json']:
 if (OUT/'live/offline_cli'/name).is_file():files.append(OUT/'live/offline_cli'/name)
files=sorted(set(files));secret_pattern=re.compile(r'(?i)(?:Bearer\s+[A-Za-z0-9._-]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{30,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,})');scan=[]
for p in files:
 rel=p.relative_to(OUT).as_posix();assert 'private_codex_home' not in rel and not rel.startswith('live/raw/') and p.name!='auth.json'
 raw=p.read_bytes();text=raw.decode('utf-8-sig',errors='replace')
 if secret_pattern.search(text):scan.append(rel)
 if p.suffix in ['.json','.jsonl'] and ('"encrypted_content":' in text or '"access_token":' in text or '"refresh_token":' in text):scan.append(rel+':private_field')
assert not scan,scan
dump('audit/PUBLIC_EXPORT_SCAN.json',{'files_scanned':len(files),'credential_pattern_matches':scan,'excluded':['live/private_codex_home','live/raw','private reasoning/SSE/CLI events','outside output CLI temp directories'],'scope':'Pattern check plus explicit inclusion policy; no auth file opened'})
files.append(OUT/'audit/PUBLIC_EXPORT_SCAN.json');files=sorted(set(files));manifest=[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files];dump('BUNDLE_MANIFEST.json',{'files':manifest,'entries':len(manifest),'excludes_manifest_self':True,'status':status['stage']});files.append(OUT/'BUNDLE_MANIFEST.json')
archive=OUT/'p3r-completion-review.zip';assert not archive.exists(),'Do not overwrite an existing final archive'
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in files:z.write(p,p.relative_to(OUT).as_posix())
with zipfile.ZipFile(archive) as z:
 bad=z.testzip();assert bad is None
 for row in manifest:assert hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256']
dump('ZIP_RECEIPT.json',{'file':archive.name,'sha256':sha(archive),'bytes':archive.stat().st_size,'entries':len(files),'all_member_hashes_verified':True,'excludes_credentials_and_private_reasoning':True})
print(json.dumps(read(OUT/'ZIP_RECEIPT.json'),ensure_ascii=False))

