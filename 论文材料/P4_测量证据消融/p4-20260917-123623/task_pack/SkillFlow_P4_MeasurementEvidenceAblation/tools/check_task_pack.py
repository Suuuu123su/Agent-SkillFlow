"""Check document-package consistency only; no SkillFlow imports or network/model calls."""
from pathlib import Path
import hashlib
import json

R=Path(__file__).resolve().parent.parent

def load(name):
    return json.loads((R/name).read_text(encoding='utf-8'))

def conjunction(xs):
    if any(x is False for x in xs): return False
    return True if all(x is True for x in xs) else None

def ests(u,v):
    if u is False or v is True: return False
    return True if u is True and v is False else None

p=load('plan.json'); v=load('ablation_profiles.json')['profiles']
assert len(v)==len({x['view_id'] for x in v})==13
assert sum(x['type']=='ablation' for x in v)==10
assert sum(x['type']=='negative_control' for x in v)==2
assert all(value==0 for value in p['budgets'].values())
assert p['publication']['auto_commit'] is False and p['publication']['auto_push'] is False
assert not p['gold_policy']['full_is_gold']
e=load('contract_examples.json')
for x in e['conjunction']: assert conjunction(x['inputs']) is x['expected']
for x in e['ests']: assert ests(x['U'],x['V']) is x['expected']
for x in e['hiaa']:
    c=x['cells']; low=c['p11'][0]-c['p10'][1]-c['p01'][1]+c['p00'][0]
    high=c['p11'][1]-c['p10'][0]-c['p01'][0]+c['p00'][1]
    assert [low,high]==x['expected']
for x in load('MANIFEST.json')['files']:
    b=(R/x['path']).read_bytes()
    assert len(b)==x['bytes'] and hashlib.sha256(b).hexdigest()==x['sha256'],x['path']
print(json.dumps({'task_pack_check':'PASS','scope':'file integrity,13 profiles,zero-call limits,and symbolic specification examples only','p4_executed':False,'skillflow_analyzer_validated':False,'model_calls':0},ensure_ascii=False,indent=2))
