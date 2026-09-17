"""Bounded delivery acceptance, no experiment launch."""
from common import *
import ast,re

offline_guard();checks=[]
def check(name,ok,detail=None):checks.append(dict(name=name,pass_check=bool(ok),detail=detail))
required=['P3R_FINAL_REPORT.md','P3R_METRIC_MAIN.md','P3R_STATUS.json','METRICS_LONG.csv','GAP_CLOSURE.csv','CLAIM_EVIDENCE_MATRIX.md','M2_DIAGNOSIS.md','M2_FIRST_FAILURES.csv','CAPABILITY_MODEL_CONTRACT.md','POT_SETS_AND_WITNESSES.json','ALR_REASON_PROVENANCE.csv','ALR_STRICT_FUNNEL.csv','RIR_LEGACY_AND_CHAIN.csv','RIR_LIFECYCLE_EVENTS.jsonl','CI_FULL_AND_STABILITY.csv','SOURCE_MANIFEST_P3R.json','METRIC_TO_DECISION_MAP.md','AFTER_P3_PLAN.md','INPUT_COVERAGE.csv','MODULE_ACCOUNTING.csv','LIVE_UNITS.csv','LIVE_RIR_COHORTS.csv','LIVE_ALR_SEVEN_CONDITIONS.csv','LIVE_SESSION_LIFECYCLE.csv','live/public/ATTEMPT_RESULT_INDEX.csv','live/public/INDEPENDENT_METRICS.json','review_slice/index.json','review_slice/recompute.py']
for f in required:check('required:'+f,(OUT/f).is_file() and (OUT/f).stat().st_size>0)
status=read(OUT/'P3R_STATUS.json');check('execution_complete',status['execution_complete']);check('partial_claims_retained',status['core_claims_supported']=='PARTIAL_NOT_ALL');check('human_review_0',status['human_review_count']==0)
r=read(OUT/'live/public/EXECUTION_AUDIT.json');check('attempts_unique',r['attempts']==r['unique_attempt_ids'] and r['duplicate_result_ids']==0);check('all_settled',not r['pending_results'] and not r['unmatched_results']);check('caps',not r['slot_cap_failures'] and r['attempts']<=1104);check('only_luna',set(r['models'])=={'gpt-5.6-luna'});check('only_actor',set(r['role_counts'])=={'actor'});check('fixed_endpoint',set(r['endpoints'])=={'https://chatgpt.com/backend-api/codex/responses'});check('frozen_source',not r['frozen_source_failures'])
check('legacy_preservation',read(OUT/'audit/HISTORICAL_PRESERVATION.json')['all_unchanged']);check('source_hashes',not read(OUT/'SOURCE_MANIFEST_P3R.json')['hash_mismatches']);v=read(OUT/'live/public/INDEPENDENT_VALIDATION.json');check('live_receipts_events',not v['failed'] and not v['checkpoint_failures']);check('independent_metrics',read(OUT/'live/public/INDEPENDENT_METRICS.json')['failed']==0)
c=read(OUT/'live/public/CONTINUITY_CHECK.json');check('checkpoint_prefix_and_grants',not c['prefix_or_grant_failures']);check('3_continuous_sessions',not c['noncontinuous']);check('portable_slice',not read(OUT/'review_slice/RECOMPUTED.json')['failed'])
g=list(csv.DictReader((OUT/'GAP_CLOSURE.csv').open(encoding='utf-8-sig')));check('G01_to_G11',set(x['id'] for x in g)=={f'G{i:02}' for i in range(1,12)});check('no_blank_gaps',all(x['actual_evidence'] and x['remaining_boundary'] for x in g))
long=list(csv.DictReader((OUT/'METRICS_LONG.csv').open(encoding='utf-8-sig')));potunknown=[x for x in long if x['metric_id']=='hiaa_pot_declared' and x.get('case')=='unknown_not_zero'];check('unknown_pot_not_zero',len(potunknown)==1 and potunknown[0]['value']=='' and potunknown[0]['upper']=='2');check('legacy_G_rir_NA',all(x['value']=='' and x['denominator']=='0' for x in long if x['analysis_layer']=='LEGACY_RECOMPUTED' and x['phase']=='g' and x['metric_id'] in ['rir_1','rir_3']))
# New offline sources must parse; no execution of live launchers or packed task scripts.
for p in (OUT/'analysis').glob('*.py'):
 try:ast.parse(p.read_text(encoding='utf-8-sig'));ok=True
 except SyntaxError:ok=False
 check('syntax:'+p.name,ok)
for f in ['P3R_FINAL_REPORT.md','README.md','REPRODUCE.md']:
 text=(OUT/f).read_text(encoding='utf-8')
 for target in re.findall(r'\]\(([^)]+)\)',text):
  if not target.startswith(('http:','https:')):check('link:'+f+':'+target,(OUT/target).exists())
dump('audit/FINAL_ACCEPTANCE.json',{'checks':len(checks),'failed':[x for x in checks if not x['pass_check']],'results':checks,'no_new_model_calls':True});print(json.dumps({'checks':len(checks),'failed':[x for x in checks if not x['pass_check']]},ensure_ascii=False));assert all(x['pass_check'] for x in checks)
