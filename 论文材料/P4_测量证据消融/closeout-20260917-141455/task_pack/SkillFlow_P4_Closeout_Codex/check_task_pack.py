"""Validate the task document pack. Does not run SkillFlow, SDKs or experiment code."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parent
plan = json.loads((root/'plan.json').read_text(encoding='utf-8'))
assert plan['execution_status'] == 'TASK_SPEC_ONLY_NOT_EXECUTED'
assert plan['limits']['full_predictor_sweeps'] == 0
assert plan['github']['commit'] is False and plan['github']['push'] is False
scope=plan['existing_scope_for_binding_only']
assert scope['queries']*scope['views'] == scope['saved_results'] == 252096
assert plan['limits']['optional_portable_query_count']*plan['limits']['optional_portable_views']==832
manifest=json.loads((root/'MANIFEST.json').read_text(encoding='utf-8'))
for row in manifest['files']:
    p=root/row['path']
    b=p.read_bytes()
    assert len(b)==row['bytes'], row['path']
    assert hashlib.sha256(b).hexdigest()==row['sha256'], row['path']
print(json.dumps({'task_pack_integrity':'PASS', 'experiment_run':False, 'P4_closeout_executed':False, 'network_requests':0},ensure_ascii=False,indent=2))
