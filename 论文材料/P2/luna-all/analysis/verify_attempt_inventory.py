"""Standalone verification using exported files only; no runner or inference imports."""
import json,sys,collections
from pathlib import Path
def main(root):
 root=Path(root);a=json.loads((root/'analysis/outputs/PHYSICAL_ATTEMPTS.json').read_text(encoding='utf-8'));q=[json.loads(s) for s in (root/'review_materials/accounting/REQUEST_ACCOUNTING.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
 ids={x['id']:x for x in q};seen=set();keys=set()
 for x in a:
  key=x['eval_id'],x['attempt'];assert key not in keys;keys.add(key)
  assert len(x['request_ids'])==x['budget_attempts']
  for i in x['request_ids']:
   assert i not in seen and i in ids;seen.add(i)
   assert ids[i]['unit']==x['eval_id'] and x['request_start_exclusive']<i<=x['request_end_inclusive']
  if x['auxiliary_assessed']:
   expected=True if x['U'] is True and x['V'] is False else False if x['U'] is False or x['V'] is True else None
   assert x['E_STS']==expected
 assert sum(x['attempt']=='first_pass' for x in a)==39
 assert len({x['eval_id'] for x in a})==39
 core={x['id'] for x in q if not x['unit'].startswith('TECH-')}
 assert seen==core,{'unassigned':sorted(core-seen),'extra':sorted(seen-core)}
 print(json.dumps({'unique_formal_stages':39,'physical_attempts':len(a),'assigned_core_requests':len(seen),'request_coverage_complete':True,'request_intervals_disjoint':True,'auxiliary_formula_valid':True,'semantic_truth_verified':False,'by_round':dict(collections.Counter(x['attempt'] for x in a))},indent=2))
if __name__=='__main__':main(sys.argv[1])
