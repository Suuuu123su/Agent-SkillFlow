"""Bind selected Luna references without reading or changing P0 semantic decisions."""
from pathlib import Path
import csv,json,hashlib,shutil
ROOT=Path(__file__).resolve().parent.parent
P0=ROOT.parent/'ClawTrojan-P0-measurement-audit-20260915-v1'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(x):return {k:v for k,v in x.items() if k!='workspace_path'}
source={x['eval_id']:x for x in read(P0/'SOURCE_MAP.json') if x['model']=='GPT-5.6-Luna' and x['method']=='Evidence'}
keys=read(ROOT/'TASK_KEYS39_BOUND.json');new={x['metadata']['eval_id']:x['config'] for x in read(ROOT/'NATIVE_MANIFEST39.json')['cases']}
rows=[];full=[]
for k in keys:
 uid=k['eval_id'];s=source[uid];case=Path(k['selected_case_dir']);oid=s['observation_id'];dest=ROOT/'reference_evidence'/uid;dest.mkdir(parents=True,exist_ok=True)
 assert sha(case/'trace.json')==k['reference_trace_sha256']==s['trace_sha256']
 candidate_path=P0/'evidence'/oid/'request_candidates.json';candidates=read(candidate_path)
 for n in ['trace.json','judge.json','native_reference_config.json','initial_files.json','selected_result.json']:
  if (case/n).is_file():shutil.copy2(case/n,dest/n)
 shutil.copy2(candidate_path,dest/'public_request_candidates.json')
 old=read(case/'native_reference_config.json')['config'];transports=sorted({x['transport'] for x in candidates});models=sorted({x['parameters'].get('model') for x in candidates})
 snapshot={p.relative_to(Path(new[uid]['workspace_path'])).as_posix():sha(p) for p in Path(new[uid]['workspace_path']).rglob('*') if p.is_file()}
 prior_initial=read(case/'initial_files.json') if (case/'initial_files.json').exists() else None
 tmatch='DIFFERENT_API_TO_ISOLATED_CLI' if 'api_endpoint_recorded' in transports else 'CLI_PERSONAL_CONTEXT_UNVERIFIED_AND_WRAPPER_CHANGED'
 row={'eval_id':uid,'sample_id':k['sample_id'],'attack':k['attack'],'reference_observation_id':oid,'reference_trace_sha256':s['trace_sha256'],'reference_source':s['selected_source'],'reference_actor_transport':'|'.join(transports),'new_actor_transport':'ISOLATED_CODEX_CLI','native_task_config_equal_except_workspace':norm(old)==norm(new[uid]),'initial_workspace_hashes_equal':prior_initial==snapshot,'native_user_request_equal':old['user_input']==new[uid]['user_input'],'native_tools_equal':old['available_tools']==new[uid]['available_tools'],'native_system_equal':old['system_prompt']==new[uid]['system_prompt'],'reference_requested_model':'|'.join(models),'new_requested_model':'gpt-5.6-luna','actor_config':'20 native turns; CLI max-output not enforceable; new wrapper/base context explicit','transport_context':tmatch,'defense_library':'13 LUNA_V3_FILES_HASH_VERIFIED; per-row executed source-chain limits retained','judge_config':'SAME_NATIVE_PROMPT_LIBRARY_REQUESTED_LUNA; '+('TRANSPORT_MISMATCH' if 'api_endpoint_recorded' in transports else 'HISTORICAL_CLI_FULL_CONTEXT_UNVERIFIED'),'physical_record_binding':s['request_binding_limit'],'reuse_marked':s['reuse_marked'],'historical_reuse_possible':s['historical_reuse_possible'],'reference_match':'HISTORY_ONLY','controlled_comparison_eligible':False,'native_reference_verdict':read(case/'judge.json')['verdict'],'new_result_status':'NOT_STARTED','new_native_verdict':None,'source_projection_sha256':sha(candidate_path),'source_trace_locator':str(dest/'trace.json')}
 rows.append(row);full.append({**row,'actual_request_anchors':s['actual_request_refs'],'public_projection_copy':str(dest/'public_request_candidates.json'),'reference_config_sha256':sha(case/'native_reference_config.json'),'contract_variant':s['contract_variant']})
with (ROOT/'REFERENCE_COMPATIBILITY39.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(ROOT/'REFERENCE_COMPATIBILITY39.json').write_text(json.dumps(full,ensure_ascii=False,indent=2),encoding='utf-8')
summary={'rows':len(rows),'attack':sum(r['attack'] for r in rows),'clean':sum(not r['attack'] for r in rows),'native_config_equal':sum(r['native_task_config_equal_except_workspace'] for r in rows),'initial_workspace_equal':sum(r['initial_workspace_hashes_equal'] for r in rows),'history_only':len(rows),'controlled_comparison_eligible':0,'reason':'API/CLI or historical unverified personal context and explicit new wrapper; no historical rejudge or rerun'}
(ROOT/'REFERENCE_COMPATIBILITY_SUMMARY.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary))
