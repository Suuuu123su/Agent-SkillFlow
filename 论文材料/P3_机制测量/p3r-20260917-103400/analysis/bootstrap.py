import json,csv,hashlib,subprocess
from pathlib import Path
O=Path(r'E:\Skill ＆ Harness\Agent\论文材料\P3_机制测量\p3r-20260917-103400');R=O.parents[2];P=O/'task_pack/SkillFlow_P3R_CompleteMetrics60'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
checks=[dict(path=x['path'],ok=sha(P/x['path'])==x['sha256'] and (P/x['path']).stat().st_size==x['bytes']) for x in json.loads((P/'MANIFEST.json').read_text())['files']]
(O/'audit/PACK_VERIFICATION.json').write_text(json.dumps(checks,indent=2));assert all(x['ok'] for x in checks)
old=O.parent/'p3-20260916-232018'
files=list(old.rglob('*'));baseline={str(p):sha(p) for p in files if p.is_file()}
for name in ['README.md','.gitignore','docs/progress.md','src/skillflow/instrumentation/file_proxy.py','src/skillflow/instrumentation/mock_tools.py','src/skillflow/instrumentation/tool_effects.py','src/skillflow/instrumentation/tool_types.py','src/skillflow/models/tool_calls.py','tests/integration/test_t14_security_isolation.py']:baseline[str(R/name)]=sha(R/name)
(O/'audit/BASELINE_HASHES.json').write_text(json.dumps(baseline,ensure_ascii=False,indent=2))
loc=list(csv.DictReader((P/'locators/LEGACY_M2_90.csv').open(encoding='utf-8-sig')))
for condition in ['m2-control-normal','m2-target-normal']:
 rows=[x for x in loc if x['phase']=='g' and ('control' in x['condition'])==('control' in condition)]
 x=rows[0]; rel,lin=x['source_ref'].split('#L'); row=json.loads((R/rel).read_text().splitlines()[int(lin)-1]); print('M2 REPRESENTATIVE',x); print('keys',row.keys());print('raw_files',json.dumps(row['raw_files']));print('decisions',json.dumps(row['decisions'])[:8000]);print('issues',row['issues']); print('data keys',row['data'].keys());print('aliases',row['data']['artifact_ids_by_alias']);print('definition',json.dumps(row['data']['analysis_definition'])[:14000])
manifest=json.loads((R/'datasets/t17-v2/stages/g/dataset-manifest.json').read_text());print('RAW STAGE',json.dumps({k:v for k,v in manifest['stages'][0].items() if k in ['raw_relative_path','raw_files']})[:12000])
