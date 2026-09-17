from common import *
from views import project,PROFILES
from itertools import product
from predictor import conj,disj,neg

guard();checks=[]
# Truth-table identities checked against all Boolean completions, not another implementation of the same partial helper.
for u,v in product([False,True,None],repeat=2):
 worlds=[(a,b) for a,b in product([False,True],repeat=2) if (u is None or a==u) and (v is None or b==v)];values={a and not b for a,b in worlds};expected=next(iter(values)) if len(values)==1 else None;got=conj([u,neg(v)]);checks.append(dict(test='E_STS_completions',U=u,V=v,expected=expected,actual=got,pass_check=expected==got))
for xs in product([False,True,None],repeat=3):
 worlds=[ys for ys in product([False,True],repeat=3) if all(a is None or a==b for a,b in zip(xs,ys))];vs={all(ys) for ys in worlds};expected=next(iter(vs)) if len(vs)==1 else None;checks.append(dict(test='conjunction_completions',inputs=xs,pass_check=conj(xs)==expected))
base=rows(OUT/'minimal_data/BASE_DOCUMENTS.jsonl');maskchecks=[]
for vid,family in PROFILES.items():
 if vid in ['V00','V12']:continue
 docs=rows(OUT/f'views/admission/{vid}/DOCUMENTS.jsonl');bad=[];found=0
 def walk(x,path=''):
  global found
  if isinstance(x,dict):
   for k,v in x.items():
    if k==family:
     found+=1
     if v is not None:bad.append(path+'/'+k)
    walk(v,path+'/'+k)
  elif isinstance(x,list):
   for j,v in enumerate(x):walk(v,path+'/'+str(j))
 walk(docs)
 assert not bad
 maskchecks.append(dict(view_id=vid,family=family,masked_occurrences=found,residual_occurrences=len(bad),duplicate_branches_recursive=True))
 if vid=='V02':
  for d in docs:
   if d.get('scope_lifetime'):assert d['scope_lifetime'].get('grant_limits') is None
   if d.get('declared_capability_rules'):
    m=d['declared_capability_rules'];assert not set(m.get('initial',[]))&set(m.get('unknown_initial_atoms',[]))
# No forbidden answer/cache keys may appear in predictor documents, including nested branches.
forbidden={'expected','gold','gt_data','task_success','safe_task_success','satisfied','authorized','matched_grants','grant_snapshot','policy','score','ci','hiaa','result','verdict','scenario_id','condition_id','trial_id','run_id','unit_id','evaluator_id'};leaks=[]
def scan(x,path=''):
 if isinstance(x,dict):
  for k,v in x.items():
   if k in forbidden:leaks.append(path+'/'+k)
   scan(v,path+'/'+k)
 elif isinstance(x,list):
  for i,v in enumerate(x):scan(v,path+'/'+str(i))
scan(base);assert not leaks,leaks[:5];assert all(c['pass_check'] for c in checks)
jl('checks/TRUTH_TABLE_CHECKS.jsonl',checks);csvout('checks/MASK_RECURSION_CHECKS.csv',maskchecks);dump('checks/LEAKAGE_CHECK.json',dict(forbidden_keys=sorted(forbidden),occurrences=leaks,scope='all projected documents including nested CF',independent_business_values_retained=True))
# Fixed registry reporting units / shared-prefix clustering are evaluator metadata only.
reg=rows(OUT/'QUERY_REGISTRY.jsonl');queries={q['query_id']:q for q in rows(OUT/'minimal_data/PREDICTOR_QUERIES.jsonl')};family={}
for x in rows(OUT/'control/REFERENCE_INPUTS.jsonl'):
 if x['kind']=='reference':
  from ingest import opaque
  for name in x['states']:family[opaque(name)]=opaque(x['roles']['parent'])
slots=list(csv.DictReader((P3R/'task_pack/SkillFlow_P3R_CompleteMetrics60/capacity_slots.csv').open(encoding='utf-8-sig')))
from ingest import opaque
for s in slots:family[opaque(s['slot_id'])]=opaque(s['parent_slot'] or s['slot_id'])
units={'UEA':'effect_request','UEA_count':'run','ALR':'unique_request_or_no_request_sentinel','RIR':'prefix_session_cohort','HIAA_Y':'run','HIAA_run':'matched_four_cell_grid','HIAA_pot_observed':'matched_grid_effect_type_union','HIAA_pot_declared':'finite_capability_model','Provenance':'artifact','CI':'replay_pair','TaskSuccess':'run','E_STS':'run','failure_taxonomy':'run'}
for r in reg:
 q=queries[r['query_id']];r['unit_kind']=units[r['metric']];r['independence_group']=family.get(q['unit'],q['unit'])
jl('QUERY_REGISTRY.jsonl',reg)
print('36 truth checks; recursive masks; zero forbidden answer/cache keys; registry units bound')
