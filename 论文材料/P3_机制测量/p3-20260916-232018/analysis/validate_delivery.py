"""Bounded delivery validation, no whole-repository CI."""
import json,csv,ast,hashlib,copy,collections,sys,os
from pathlib import Path
OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[2];READS=set();BINDINGS=[]
for node in ast.parse((OUT/'analysis/independent.py').read_text('utf-8-sig')).body:
 if isinstance(node,ast.FunctionDef) and node.name in ('guard','dump','jl','csvout','unique','selected'):exec(compile(ast.Module(body=[node],type_ignores=[]),'<helpers>','exec'))
sys.addaudithook(guard)
def read(n):return json.loads((OUT/n).read_text('utf-8'))
def rows(n):return [json.loads(x) for x in (OUT/n).open(encoding='utf-8')]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
checks=[]
def ck(name,result,detail=None):checks.append({'check':name,'passed':bool(result),'detail':detail})
for p in (OUT/'analysis').glob('*.py'):
 try:compile(p.read_text('utf-8-sig'),str(p),'exec');ck('python_syntax:'+p.name,True)
 except Exception as e:ck('python_syntax:'+p.name,False,str(e))
long=rows('METRICS_LONG.jsonl');runs=rows('facts/RUNS.jsonl');effects=rows('facts/EFFECTS.jsonl');replays=rows('facts/REPLAYS.jsonl');requests=rows('facts/ALL_AUTHORIZATION_REQUESTS.jsonl');claims=rows('facts/AUTHORIZATION_REQUESTS.jsonl')
ck('metric_rows',len(long)==980);ck('contracts_match_all_metrics',{r['metric_id'] for r in long}=={c['metric_id'] for c in read('METRIC_CONTRACTS.json')['metrics']})
ck('all_core_fact_count',len(runs)==1038);ck('all_replay_terminal_count',len(replays)==846)
ck('independent_main_checks',read('RECOMPUTE_CHECK.json')['failed']==0 and read('RECOMPUTE_CHECK.json')['passed']==1326)
ck('historical_980_full_objects',len(read('audit/HISTORICAL_COMPARISON.json'))==980 and all(x['full_measurement_match'] for x in read('audit/HISTORICAL_COMPARISON.json')))
for phase,n,d in [('f',360,270),('g',360,270),('h',270,270),('e',24,18),('g_canary',24,18)]:
 rs=[r for r in runs if r['phase']==phase];ps=[r for r in replays if r['phase']==phase];ck('unique_core_'+phase,len(rs)==n and len({r['unit_id'] for r in rs})==n and len({r['run_id'] for r in rs})==n);ck('unique_replay_'+phase,len(ps)==d and len({r['unit_id'] for r in ps})==d)
ck('F_H_no_duplicates',len({r['unit_id'] for r in runs if r['phase'] in ('f','h')})==630)
ck('run_uea_unit_weights',all(r['uea_weight']==r['uea_count'] for r in runs));ck('effects_receipted',all(e['receipt_bound'] and e['executed'] for e in effects))
ck('G_RIR_not_zero',all(r['value'] is None and r['denominator']==0 for r in long if r['phase']=='g' and r['metric_id'] in ('rir_1','rir_3')))
ck('HIAA_contrast_no_fake_denominator',all(r['numerator'] is None and r['denominator'] is None for r in long if r['metric_id'].startswith('hiaa.') and r['metric_id'].endswith(('scheduled','valid_only'))))
ck('negative_ci_retained',sum(r.get('ci')==-1 for r in replays if r['phase']=='f')==4 and sum(r.get('ci')==-1 for r in replays if r['phase']=='g')==2)
ck('strict_reason_never_imputed',all(r['explicit_baseline_reason'] is None for r in claims))
# Original data / source byte integrity rechecked after analysis, without writing them.
manifest=read('SOURCE_MANIFEST.json');mismatches=[];verified=0
for record in manifest['sources']:
 p=Path(record['path']);p=p if p.is_absolute() else ROOT/p
 if p.exists() and record.get('sha256'):
  verified+=1
  if sha(p)!=record['sha256']:mismatches.append(str(p))
for inventory in ('audit/TOP_LEVEL_PARTS_VERIFICATION.json','audit/T18_HASH_VERIFICATION.json','audit/ANALYSIS_CODE_MANIFEST.json'):
 for record in read(inventory):
  p=ROOT/record['path'];verified+=1
  if not p.exists() or sha(p)!=record['sha256']:mismatches.append(str(p))
ck('original_input_and_code_hashes_unchanged',not mismatches,{'files_checked':verified,'mismatches':mismatches})
# Receipt failure controls operate on in-memory copies of a saved fact; no business replay.
p=ROOT/'datasets/t17-v2/stages/f/core-trials.jsonl'
for line in p.open(encoding='utf-8'):
 c=json.loads(line)
 if c['data'] and c['data']['facts']['effects']:break
facts=c['data']['facts'];sel=c['data']['metadata']['harm_selector'];ck('positive_receipted_selector',bool(selected(facts,sel)))
bad=copy.deepcopy(facts);bad['receipts'][0]['effect_id']='deliberately-mismatched-effect'
try:selected(bad,sel);ok=False
except ValueError:ok=True
ck('mismatched_receipt_rejected',ok)
bad=copy.deepcopy(facts);target=bad['effects'][0]['request_event_id'];next(e for e in bad['events'] if e['event_id']==target)['run_id']='different-run'
try:selected(bad,sel);ok=False
except ValueError:ok=True
ck('cross_run_receipt_binding_rejected',ok)
bad=copy.deepcopy(sel);bad['source_pattern']='context:/unrelated-source';ck('unrelated_effect_not_hiaa',selected(facts,bad)==[])
try:sys.audit('socket.connect',None,None);ok=False
except RuntimeError:ok=True
ck('network_guard_rejects_connect_without_network',ok)
try:sys.audit('subprocess.Popen',None,None,None,None);ok=False
except RuntimeError:ok=True
ck('process_guard_rejects_spawn_without_spawn',ok)
# Additional request denominator funnel from cached actual requests.
mode={(r['phase'],r['run_id']):r['mode'] for r in runs}
for r in requests:r['mode']=mode[(r['phase'],r['run_id'])]
jl('facts/ALL_AUTHORIZATION_REQUESTS.jsonl',requests)
populations=[]
for phase in read('facts/FRESH_VECTORS.json'):
 def member(r):return r['phase'] in ('f','h') and r['mode']==phase[3:] if phase.startswith('fh_') else r['phase']==phase
 rr=[r for r in requests if member(r)];qq=[r for r in claims if member(r)];populations.append({'phase':phase,'actual_unique_authorization_requests':len({(r['run_id'],r['request_id']) for r in rr}),'sensitive_requests_sensitivity_gt0':sum((r['effect'] or {}).get('sensitivity',0)>0 for r in rr),'registered_claim_requests':len(qq),'eligible_low_trust_claim_requests':sum(r['eligible'] for r in qq),'v2_confirmed_laundering':sum(r['laundering'] is True for r in qq),'explicit_reason_missing':sum(r['explicit_baseline_reason'] is None for r in qq),'note':'sensitivity>0 is an exposure inventory descriptor, not a replacement ALR denominator'})
csvout('tables/ALR_REQUEST_POPULATIONS.csv',populations)
b=read('facts/EVIDENCE_BOUNDARIES_SIX.json');ck('bounded_static_examples',len(b)==6);ck('selected_checks_and_enforcer_bound',all(x['requested_components']==x['performed_components'] and x['saved_enforcer_consumption'] for x in b));ck('no_future_endpoint_in_six_inputs',all(x['future_actor_outcome'] is None and not x['aggregate_metric_fields'] for x in b))
ck('frozen_luna_static_hashes',all(x['same_bytes'] and x['matches_luna_freeze'] for x in read('audit/EVIDENCE_SOURCE_BINDING.json')))
t18=read('audit/T18_RAW_ENDPOINT_CHECKS.json');ck('t18_308_endpoints',len(t18)==308 and all(all(x[k] for k in ('task_match','safe_task_match','uea_match','target_match')) for x in t18))
with (OUT/'tables/HIAA_CONSTRUCT_CHECKS.csv').open(encoding='utf-8-sig') as f:cc=list(csv.DictReader(f))
ck('hiaa_structural_controls',all(x[k]=='True' for x in cc for k in ('four_cells','same_selector','same_normal_task_obligations','same_normalized_grants','only_shared_context_harness_axis','frozen_skill_pair_capability_match')))
# File and internal link review.
required=['P3_FINAL_REPORT.md','P3_METRIC_MAIN.md','METRIC_CONTRACTS.json','METRICS_LONG.csv','METRICS_LONG.jsonl','GAP_LIST.md','CLAIM_EVIDENCE_MATRIX.md','METRIC_TO_DECISION_MAP.md','FUTURE_PLAN.md','P3_STATUS.json','SOURCE_MANIFEST.json','RECOMPUTE_CHECK.json','progress.html']
ck('required_deliverables_present',all((OUT/n).is_file() and (OUT/n).stat().st_size for n in required))
result={'scope':'targeted offline checks; not full or remote CI','checks':checks,'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks),'new_live_calls':0,'new_replays':0}
dump('audit/DELIVERY_VALIDATION.json',result)
print('VALIDATION',result['passed'],result['failed'],'original files verified',verified)
if result['failed']:print([x for x in checks if not x['passed']]);raise SystemExit(1)
