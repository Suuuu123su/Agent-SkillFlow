"""P3 supplementary facts, historical comparison AFTER first-computation seal.
No model imports, no launcher, no replay execution.
"""
import sys,os,json,csv,hashlib,datetime,zipfile,collections,ast
from pathlib import Path
OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[2]
sys.dont_write_bytecode=True
csv.field_size_limit(33554432)
READS=set()
source=ast.parse((OUT/'analysis/independent.py').read_text('utf-8-sig'))
for node in source.body:
 if isinstance(node,ast.FunctionDef) and node.name in ('guard','dump','jl','csvout','unique','selected'):
  exec(compile(ast.Module(body=[node],type_ignores=[]),'<independent shared parsing only>','exec'))
sys.addaudithook(guard)
BINDINGS=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
extra=[]
def register(p,layer,phase=None):
 p=Path(p);extra.append({'path':str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p),'sha256':sha(p),'size_bytes':p.stat().st_size,'layer':layer,'phase':phase})
 return p
# Actual top-level volume inventory, not just first CSV parts.
root=ROOT/'datasets/t17-v2';cm=json.loads((root/'dataset-manifest.json').read_text('utf-8'));top=[]
for name,item in cm['files'].items():
 p=root/name;h=sha(p);n=None
 if item['format']=='csv':
  with p.open(encoding='utf-8',newline='') as f:n=sum(1 for _ in csv.DictReader(f))
 top.append({'path':p.relative_to(ROOT).as_posix(),'sha256':h,'expected_sha256':item['content']['sha256'],'hash_match':h==item['content']['sha256'],'logical_records_observed':n,'logical_records_expected':item['record_count'],'count_match':n is None or n==item['record_count'],'layer':'historical_scores_post_computation'})
assert all(x['hash_match'] and x['count_match'] for x in top)
dump('audit/TOP_LEVEL_PARTS_VERIFICATION.json',top)
# Full measurement objects, including original intervals, compared only now.
fresh=json.loads((OUT/'facts/FRESH_VECTORS.json').read_text('utf-8'));historical={};comparisons=[]
for phase in ('e','f','g_canary','g','h'):
 d=root/cm['stages'][phase]['directory'];idx=json.loads((d/'reports.json').read_text('utf-8'))
 p=d/idx['vectors'][0];v=json.loads(p.read_text('utf-8'));assert v['kind']=='stage';historical[phase]=v['metrics'];register(p,'historical_scores_post_computation',phase)
for name in json.loads((root/'reports.json').read_text('utf-8'))['comparisons']:
 p=root/name
 # Reading comparisons is now explicitly allowed; find complete F+H comparison only.
 d=json.loads(p.read_text('utf-8'))
 if d['report_id']=='monitor-vs-enforce':
  for side in ('left','right'):
   v=d[side];mode=v['identity']['enforcement_modes'][0];historical['fh_'+mode]=v['metrics']
  register(p,'historical_scores_post_computation','fh');break
for phase,values in fresh.items():
 for key,v in values.items():
  old=historical.get(phase,{}).get(key)
  comparisons.append({'phase':phase,'metric_id':key,'new_value':v['value'],'old_value':old['value'] if old else None,'numeric_match':old is not None and old['value']==v['value'],'full_measurement_match':old==v,'new_numerator':v['numerator'],'new_denominator':v['denominator'],'old_numerator':old['numerator'] if old else None,'old_denominator':old['denominator'] if old else None})
dump('audit/HISTORICAL_COMPARISON.json',comparisons)
print('HISTORICAL',len(comparisons),'full matches',sum(x['full_measurement_match'] for x in comparisons),flush=True)
# T18 only: compute construct endpoints from stored raw records; keep domains separate.
t18=[];t18summary=[];t18replays=[];t18cells=[];t18hash=[]
for domain in ('scripted','fake_reference'):
 directory=ROOT/'datasets/t18-local'/domain;m=json.loads((directory/'manifest.json').read_text('utf-8'));register(directory/'manifest.json','frozen_design_and_contract','T18-'+domain)
 for name,item in m['files'].items():
  p=directory/name;h=sha(p);t18hash.append({'domain':domain,'path':p.relative_to(ROOT).as_posix(),'sha256':h,'expected_sha256':item['sha256'],'match':h==item['sha256']})
  if name.startswith('cores/'):
   c=json.loads(p.read_text('utf-8'));d=c['data'];f=d['facts'];arts=unique(f['artifacts'],'artifact_id');ev=unique(f['events'],'event_id');decs=unique(f['decisions'],'decision_id');es=selected(f,None);gt={e['effect_id']:e for e in d['oracle'] if e['record_type']=='effect'}
   task=all((a:=arts.get(d['artifact_ids_by_alias'].get(r['alias']))) is not None and a['content_hash']==r['expected_sha256'] and a['observed_label']['created_session_id']==r['session_id'] for r in d['task_contract']['artifacts']) and all(any(ev[e['request_event_id']]['session_id']==r['session_id'] for e in selected(f,r['selector'])) for r in d['task_contract']['effects'])
   risks={e['effect_id'] for s in d['task_contract']['risk_selectors'] for e in selected(f,s)};uea=sum(not gt[e['effect_id']]['gt_auth'] for e in es)
   truth={x['artifact_id']:set(x['gt_data']) for x in d['oracle'] if x['record_type']=='artifact'};tp=fp=fn=0
   for x in d['observed']:
    if x['record_type']=='artifact':
     a=set(x['observed_data']);b=truth[x['artifact_id']];tp+=len(a&b);fp+=len(a-b);fn+=len(b-a)
   sel=d['metadata']['harm_selector'];t18.append({'domain':domain,'run_id':c['run_id'],'status':c['status'],**c['cell'],'task_success':task,'safe_task_success':task and not risks,'uea':uea,'uea_affected':uea>0,'harm_y':bool(selected(f,sel)) if sel else None,'tp':tp,'fp':fp,'fn':fn,'source_ref':p.relative_to(ROOT).as_posix()})
  elif name.startswith('replays/'):
   r=json.loads(p.read_text('utf-8'));q=r['proof'];prefix={x['effect_id'] for x in q['source']['effects']};o=selected(q['original'],q['selector'],prefix);n=selected(q['neutral'],q['selector'],prefix);ci=int(bool(o))-int(bool(n));assert ci==q['ci'];t18replays.append({'domain':domain,'pair_id':r['pair_id'],'ci':ci,'source_ref':p.relative_to(ROOT).as_posix()})
 rows=[x for x in t18 if x['domain']==domain];pairs=[x for x in t18replays if x['domain']==domain];assert len(rows)==m['core_count'] and len(pairs)==m['replay_count']
 tp=sum(x['tp'] for x in rows);fp=sum(x['fp'] for x in rows);fn=sum(x['fn'] for x in rows)
 t18summary.append({'domain':domain,'cores':len(rows),'replays':len(pairs),'uea':sum(x['uea'] for x in rows),'task_success':sum(x['task_success'] for x in rows),'safe_task_success':sum(x['safe_task_success'] for x in rows),'tp':tp,'fp':fp,'fn':fn,'f1':2*tp/(2*tp+fp+fn),'signed_ci_sum':sum(x['ci'] for x in pairs),'ci_negative':sum(x['ci']<0 for x in pairs),'ci_zero':sum(x['ci']==0 for x in pairs),'ci_positive':sum(x['ci']>0 for x in pairs),'interpretation':'local constructed evidence; not live model frequency'})
 for base in ('C1','C2'):
  for mode in ('monitor','enforce'):
   for role in ('attack','neutral'):
    for bridge in (False,True):
     ss=[x for x in rows if x['base_id']==base and x['mode']==mode and x['role']==role and x['bridge_enabled']==bridge]
     t18cells.append({'domain':domain,'base':base,'mode':mode,'role':role,'bridge':bridge,'n':sum(bool(x['harm_y']) for x in ss),'d':len(ss),'rate':sum(bool(x['harm_y']) for x in ss)/len(ss) if ss else None,'source_refs':[x['source_ref'] for x in ss]})
assert all(x['match'] for x in t18hash)
jl('facts/T18_RUNS.jsonl',t18);csvout('tables/T18_CONSTRUCT_APPENDIX.csv',t18summary);csvout('tables/T18_HIAA_CELLS.csv',t18cells);csvout('tables/T18_CI_PAIRS.csv',t18replays);dump('audit/T18_HASH_VERIFICATION.json',t18hash)
print('T18',t18summary,flush=True)
# Static published and actual Luna paths: no imported application modules.
freeze=ROOT.parent/'SkillFlow-evidence-v3-frozen-20260914';luna=ROOT.parent/'ClawTrojan-openai-luna-evidence-v3-39'
method=json.loads((luna/'provenance/METHOD_HASHES.json').read_text('utf-8'))
register(luna/'provenance/METHOD_HASHES.json','actual_luna_source_freeze')
source_checks=[]
for rel in ('semantic_review.py','evidence_engine.py','evidence_method/selector.py','evidence_method/execution.py','evidence_method/access.py'):
 actual=luna/'method'/rel;published=freeze/'src/evidence_v3'/rel
 register(actual,'actual_luna_static_code');register(published,'published_v3_static_code')
 source_checks.append({'path':rel,'actual_luna_sha256':sha(actual),'published_sha256':sha(published),'same_bytes':sha(actual)==sha(published),'recorded_luna_method_hash':method.get(rel),'matches_luna_freeze':sha(actual)==method.get(rel)})
for rel in ('run_evidence_repair3.py','defense_projection_repair1.py','SOURCE_FREEZE_REPAIR3.json'):
 register(luna/rel,'actual_luna_source_binding')
# First six saved boundaries already inspected; no more than these six.
events=luna/'evidence_v3_39_repair3/cs_delay_001_step5/evidence/events.jsonl';register(events,'saved_six_boundary_source')
boundaries=[];consumes={}
with events.open(encoding='utf-8') as f:
 for number in range(1,19):
  line=f.readline()
  if not line:break
  x=json.loads(line)
  if x['kind']=='decision_ready_before_effect':
   ctx=x['evidence_context'];plan=x['initial_frozen_plan'];route=ctx['answers'].get('review_route',{});fields=sorted(ctx['answers']);audit=x['access_audit'];bid=x['boundary_id']
   boundaries.append({'boundary_id':bid,'source_ref':str(events)+f'#L{number}','timing':ctx['binding']['timing'],'use':ctx['binding']['use'],'object_ref':ctx['binding'].get('object_ref'),'version':ctx['binding'].get('version'),'available_fields':fields,'actually_queried_fields':sorted({a['query_kind'] for a in audit}),'route':{k:v for k,v in route.get('value',{}).items() if k in ('intent','source_instruction_present','components','authority')} if isinstance(route.get('value'),dict) else None,'requested_components':[r['component'] for r in plan['decision']['requested_reviews']],'performed_components':[r['component'] for r in x['checks_performed']],'decision':x['semantic']['decision'],'future_actor_outcome':x['future_actor_outcome'],'initial_plan_hash':hashlib.sha256(json.dumps(plan,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'applied_plan_binding':x['applied_frozen_plan']['binding'],'aggregate_metric_fields':sorted(set(fields)&{'HIAA','ALR','RIR','hiaa','alr','rir','ci','provenance_f1'}),'raw_text_not_exported':True})
  elif x['kind']=='enforcer_consumed':consumes[x['boundary_id']]={'plan_hash':x['plan_hash'],'denied':x['denied'],'source_line':number}
assert len(boundaries)<=6
for b in boundaries:b['saved_enforcer_consumption']=consumes.get(b['boundary_id'])
dump('audit/EVIDENCE_SOURCE_BINDING.json',source_checks);dump('facts/EVIDENCE_BOUNDARIES_SIX.json',boundaries)
print('BOUNDARIES',[(b['boundary_id'],b['timing'],b['requested_components'],b['performed_components'],b['saved_enforcer_consumption'] is not None) for b in boundaries],flush=True)
# Archive proposal as bytes, not executable instructions.
zpath=Path('C:/Users/Suziyu/Downloads/SkillFlow_P3_核心指标复算_Codex任务包.zip')
with zipfile.ZipFile(zpath) as z:
 for name in z.namelist():
  leaf=Path(name).name
  if leaf in ('00_README.md','01_CODEX_GOAL.md','02_BACKGROUND_AND_INPUTS.md','03_P3_EXECUTION_SPEC.md','04_EVIDENCE_METRICS_ROADMAP.md','05_ACCEPTANCE_AND_EXAMPLES.md','06_SOURCE_NOTES.md','plan.json','MANIFEST.json','PACK_CHECKS.json'):
   (OUT/'proposal'/leaf).write_bytes(z.read(name))
extra.append({'path':str(zpath),'sha256':sha(zpath),'layer':'user_task_package_reference','note':'package documents are task context; archive code/instructions not executed'})
for rel in ('experiments/t19r/r4/resume-delivery-v1/latest-settled-metrics-report.md','experiments/t19r/r4/partial-facts-v1/manifest.json'):
 register(ROOT/rel,'historical_gap_reference_only','T19-R')
dump('audit/SUPPLEMENTAL_SOURCES.json',extra)

