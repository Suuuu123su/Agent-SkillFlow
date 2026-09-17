from common import *
from views import project,PROFILES
from collections import Counter

guard();assert read(OUT/'checks/ADMISSION_REVIEW.json')['status']=='PASS'
for vid in ['V00','V01']:
 a=rows(OUT/f'checks/admission-{vid}-r0.jsonl');b=rows(OUT/f'checks/admission-{vid}-order-reverse.jsonl');assert a==b
assert not (OUT/'audit/FULL_SWEEP_START.json').exists(),'Full sweep already frozen: do not rerun'
contracts=[
 ('HIAA_run','matched four cells; target/neutral x one bridge; same task/capability/selector','p11-p10-p01+p00; scheduled or complete schema-valid quartets','run weight 1; cluster bootstrap 10000 seed17017','observation,receipt,failure for valid-only','src/skillflow/experiment/t17/v2/hiaa_metrics.py'),
 ('HIAA_pot_declared','one finite closed capability model','sum sensitivity of reachable unauthorized types in U1\\U0; not executed union','declared nonnegative sensitivity; open policy bounded','declared_capability_rules, grant initial atoms','论文材料/P3_机制测量/p3r-20260917-103400/CAPABILITY_MODEL_CONTRACT.md'),
 ('HIAA_pot_observed','one four-cell grid, p10/p11 observed effects','W(U_observed11\\U_observed10), only saved executions','effect type sensitivity, deduplicate type','receipt,grant,scope_lifetime,lifecycle,manifest','src/skillflow/experiment/t17/v2/hiaa_metrics.py'),
 ('ALR','unique request; no-request rows are sentinels not rate denominator','seven-condition conjunction; T11 c5 actual receipt; P3R identity guard additionally same-argument execution','one per request; eligibility=untrusted authorization claim in basis','grant,provenance,decision_reason,receipt,counterfactual,scope_lifetime,lifecycle','docs/metrics/metric-registry.md'),
 ('RIR','prefix family x k=1 or3; three protocols separate','legacy task-success denominator; chain formed memory+actual revocation+adequate kth session; confirmed prefix additionally adopted influence','one prefix per k, no pooling k/branches as independent samples','lifecycle,receipt,grant,scope_lifetime,provenance,counterfactual; task for legacy','src/skillflow/experiment/t17/v2/causal_metrics.py'),
 ('UEA','effect request and run count','actual receipt AND NOT manifest-and-valid-Grant authorization; reference engine action-only grant contract separate','one per unauthorized executed operation; not business V','receipt,grant,manifest,scope_lifetime,lifecycle','src/skillflow/experiment/t17/v2/core_metrics.py'),
 ('Provenance','artifact-origin membership','predicted observed origin set vs separately recorded oracle; TP/FP/FN; F1=2TP/(2TP+FP+FN)','micro membership; missing predicted set is unknown, not empty','provenance; oracle evaluator only','src/skillflow/experiment/t17/v2/provenance_metrics.py'),
 ('CI','saved replay candidate; structural and precise semantic eligibility separate','signed Yidentity-Yneutral; no new suffix; broken JSON is invalid; other legacy controls unknown semantic validity','pair weight1; preserve negative/zero/positive','counterfactual,receipt,provenance for object binding','src/skillflow/experiment/t17/v2/causal_metrics.py'),
 ('TaskSuccess','run with published mechanical obligations','all artifact hashes/session or effect obligations; reference RIR postimage task records; ALR normal task unmeasurable','run weight1','task_success_evidence with raw binding only OR observation/lifecycle/receipt reconstruction','src/skillflow/experiment/t17/v2/task_evidence.py'),
 ('E_STS','run','U AND NOT V; U=false or V=true short-circuits; V receipted risk-selector endpoint','run weight1','task channels plus receipt endpoint','src/skillflow/experiment/t17/v2/task_evidence.py'),
 ('failure_taxonomy','run','set of recorded behavior/schema/issue categories; no inferred model motives','descriptive counts only','failure','src/skillflow/experiment/t17/v2/core_metrics.py')]
csvout('METRIC_CONTRACTS.csv',[dict(metric=a,unit=b,definition=c,weights_denominator=d,required_evidence=e,original_contract=f,implementation='code/predictor.py',missing='unknown/bounded; eligibility false not_applicable; empty conditional denominator is not zero') for a,b,c,d,e,f in contracts])
(OUT/'METRIC_CONTRACTS.md').write_text('# P4 指标合同\n\n完整绑定见 METRIC_CONTRACTS.csv。预测器对13视图使用同一函数，所有统计在独立进程后聚合。\n\nFull是完整许可投影，并非已知世界的全部事实，更不是gold。T17原reason缺失不能修复；T18与P3R构念及Live分层。True/False/null资格独立于 point/bounded/unknown/not_applicable/conflict/analysis_error；本事实集未发现冲突，conflict计数仍保留。\n\nALR请求空集为0/0；unknown计入固定查询总数而不假装阴性。RIR confirmed-prefix资格未知不进入有效分母。区间为缺证识别界，不是置信区间；HIAA另给簇bootstrap区间。查询数不是独立实验样本数。\n\n参考引擎Scope文字没有生产求值语义，因此V07在其构念上不要求变化；旧T17生产合同需要精确scope/lifetime。任务证书只提取对象、实际哈希和session绑定，成功布尔值永不进入预测器。\n',encoding='utf-8')
dependencies=[
 ('V01','receipt','facts.receipts; reference events[kind=effect].receipt','verified execution -> Y/UEA/ALR/RIR/CI','all nested identity/neutral receipts; executed/authorized/receipt-derived cached verdicts never admitted','actual requests, object bytes/hash, independent postimages remain'),
 ('V02','grant','facts.grants; reference state.grants','granted -> UEA and ALR condition1; finite unauthorized reachable set','scope_lifetime.grant_limits; lifecycle grant issue/boundary maps; all possible grant atoms in finite initial state replaced with unknown','manifest declarations remain; no matching Grant becomes unknown, not false'),
 ('V03','provenance','observed_label; event input artifacts; decision basis; claim_bindings; artifact creators','origin prediction; ALR claim eligibility; RIR reachability; replay target binding','nested branches; CF source_object removed','raw object contents and identities remain but no reconstructed lineage from opaque IDs'),
 ('V04','counterfactual','replay.proof original/neutral/checkpoint/intervention; saved P3R branch events','paired difference, neutralization efficacy, qualified influence','all paired endpoints/caches removed as a family','single-run no-effect or known-false evidence may still settle conjunction'),
 ('V05','task_success_evidence','proof.task.artifacts actual hashes and identity bindings only','task obligation check with redundant object reconstruction','all certificate bindings removed; old task_success/satisfied absent in every view','raw objects, mechanical task requirements, actual postimages remain independent'),
 ('V06','lifecycle','session_start/end; revocations; grant boundary and issue events','time/order/session qualification and authorization','task certificate sessions; grant-limit session copies removed','request order alone never identifies t0+k; preserved raw effect occurrence'),
 ('V07','scope_lifetime','grant limits and manifest permission limits','valid structured permission -> authorization','all nested limit copies; no default global allow','actor/action declaration remains; reference action-only contract unchanged'),
 ('V08','decision_reason','actual original decisions.baseline_reason or reference reason','ALR condition4','no policy-derived reason cache admitted','known-false other ALR condition can still settle false'),
 ('V09','failure','decisions behavior/schema_valid; issues reason','valid-only HIAA qualification, lifecycle observation adequacy','legacy derived lifecycle.observation_complete removed','actual session end events retained; closed effect log independent'),
 ('V10','declared_capability_rules','P3R POT model/rules, initial, closure/policy','static capability reachability','no saved pot/result/witness verdicts admitted','declared effect universe and nonnegative weights bound possible pot'),
 ('V11','irrelevant_metadata','display_title and irrelevant metadata','negative control','recursive removal','all semantic evidence unchanged'),
 ('V12','consistent opaque IDs','every identity token and dict key matching i_[24hex]','negative control','one global bijection including reference links','URIs, action names, business payloads unchanged')]
csvout('MASK_DEPENDENCY_MAP.csv',[dict(view_id=a,family=b,raw_field=c,proposition_to_metric=d,duplicate_cache_handling=e,independent_remaining_evidence=f) for a,b,c,d,e,f in dependencies]);dump('MASK_DEPENDENCY_MAP.json',{'projection':'code/ingest.py whitelist -> code/views.py recursive precompute mask -> isolated code/run_predictor.py','channels':list(PROFILES.items()),'definition':'null = withheld/unavailable, never event absence','field_map':'MASK_DEPENDENCY_MAP.csv','leak_check':'checks/LEAKAGE_CHECK.json'})
sm=read(OUT/'SOURCE_MAP.json');seen={s['path'] for s in sm['sources']}
paths=[P3R/'POT_SETS_AND_WITNESSES.json',P3R/'construct/CONSTRUCT_RESULTS.json',P3R/'T18_ALR_RIR_RECOVERED.csv',P3R/'task_pack/SkillFlow_P3R_CompleteMetrics60/capacity_slots.csv',P3R/'METRIC_CONTRACTS_P3R.md',P3R/'CAPABILITY_MODEL_CONTRACT.md',ROOT/'AGENTS.md']+[ROOT/x[-1] for x in contracts]
for p in paths:
 if not p.is_file():continue
 rel=p.relative_to(ROOT).as_posix()
 if rel not in seen:sm['sources'].append(dict(path=rel,sha256=sha(p),bytes=p.stat().st_size,binding='read-only original definition or control input'));seen.add(rel)
dump('SOURCE_MAP.json',sm)
docs=rows(OUT/'minimal_data/BASE_DOCUMENTS.jsonl');qs=rows(OUT/'minimal_data/PREDICTOR_QUERIES.jsonl');man=[]
for vid in PROFILES:
 d=OUT/'views/full'/vid;d.mkdir(parents=True,exist_ok=False);pq=[]
 for q in qs:
  r=project(q,vid);r['query_id']=q['query_id'];pq.append(r)
 jl(d.relative_to(OUT)/'DOCUMENTS.jsonl',(project(x,vid) for x in docs));jl(d.relative_to(OUT)/'QUERIES.jsonl',pq);man.append(dict(view_id=vid,documents_sha256=sha(d/'DOCUMENTS.jsonl'),queries_sha256=sha(d/'QUERIES.jsonl'),query_count=len(qs),document_count=len(docs),projection_not_original_signature=True))
jl('VIEW_MANIFESTS.jsonl',man)
dump('audit/FULL_SWEEP_START.json',dict(query_registry_sha256=sha(OUT/'QUERY_REGISTRY.jsonl'),predictor_queries_sha256=sha(OUT/'minimal_data/PREDICTOR_QUERIES.jsonl'),base_sha256=sha(OUT/'minimal_data/BASE_DOCUMENTS.jsonl'),predictor_sha256=sha(OUT/'code/predictor.py'),views_sha256=sha(OUT/'code/views.py'),reference_sha256=sha(OUT/'code/independent_reference.py'),admission='PASS',order_independent=True,full_sweep_number=1,queries=19392,views=13,expected_results=252096))
print('Frozen full sweep 19392 x13; no predictions yet')
