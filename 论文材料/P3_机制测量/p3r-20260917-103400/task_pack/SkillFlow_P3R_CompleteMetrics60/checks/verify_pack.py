"""Validate the task pack, NOT SkillFlow, API behavior, or research results."""
from pathlib import Path
import csv,hashlib,json
r=Path(__file__).resolve().parents[1]
p=json.loads((r/'plan.json').read_text(encoding='utf-8'))
rows=list(csv.DictReader((r/'capacity_slots.csv').read_text(encoding='utf-8').splitlines()))
assert len(rows)==len({x['slot_id'] for x in rows})==60
assert sum(int(x['max_requests']) for x in rows)==1104
assert p['capacity']['stage_attempt_hard_cap']==1152
assert sum(x['module']=='RIR' for x in rows)==40
assert sum(x['module']=='ALR' for x in rows)==16
assert sum(x['module']=='TECH' for x in rows)==4
prefix={x['slot_id'] for x in rows if x['kind']=='prefix'}
assert len(prefix)==12
assert all(x['parent_slot'] in prefix for x in rows if x['kind']=='suffix')
assert p['legacy_data_mutable'] is False and p['new_router_algorithm'] is False
assert p['new_glm_requests']==p['new_ds_requests']==0
m=json.loads((r/'MANIFEST.json').read_text(encoding='utf-8'))
for e in m['files']:
 b=(r/e['path']).read_bytes()
 assert len(b)==e['bytes'] and hashlib.sha256(b).hexdigest()==e['sha256'],e['path']
print(json.dumps({'document_pack_validation':'PASS','capacity_slots':60,'calculated_request_cap':1104,'outer_cap':1152,'new_model_calls':0,'actual_skillflow_tests_executed':False},ensure_ascii=False,indent=2))
