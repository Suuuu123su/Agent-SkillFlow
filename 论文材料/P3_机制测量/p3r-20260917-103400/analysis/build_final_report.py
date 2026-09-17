"""Build final offline report from persisted measurements; no model dispatch."""
from common import *
from collections import Counter
import shutil,time

offline_guard()
def cr(name):return list(csv.DictReader((OUT/name).open(encoding='utf-8-sig')))
def md(name,text):(OUT/name).write_text(text.rstrip()+'\n',encoding='utf-8')
def tab(headers,rs):return '|'+ '|'.join(headers)+'|\n|'+'|'.join(['---']*len(headers))+'|\n'+''.join('|'+ '|'.join(str(x).replace('|','/').replace('\n',' ') for x in r)+'|\n' for r in rs)
def fmt(x):return 'N/A' if x is None or x=='' else f'{float(x):.6g}'
def rate(n,d):return f'{n}/{d} = {fmt(n/d)}' if d else f'{n}/0 = N/A'
S=read(OUT/'audit/RECOVERED_SUMMARY.json'); live=read(OUT/'live/public/LIVE_SUMMARY.json'); ledger=read(OUT/'live/ledger.json'); old=cr('legacy/METRICS_LONG.csv'); ix={(x['phase'],x['metric_id']):x for x in old}
formal=[v for k,v in ledger['units'].items() if not k.startswith('TECH')]; complete=all(v['status'] not in ['not_started','running'] for v in formal) and ledger['requests']['in_flight']==0
stage='P3R_EXECUTION_COMPLETE' if complete else 'IN_PROGRESS'
# Record layers without changing copied historical rows or their original source references.
long=[dict(x,analysis_layer='LEGACY_RECOMPUTED',p3r_note='Original P3 row retained; see P3R contracts and independent checks for strengthened audit/limitations',legacy_locator_base='../p3-20260916-232018/') for x in old]
def add(metric,domain,version,num,den,value=None,unknown=0,source='',limits='',phase='',extra=None):
 r=dict(study='P3R',phase=phase,domain=domain,metric_id=metric,contract_version=version,analysis_layer='NEW_LIVE_SUPPLEMENT' if domain=='LUNA_LIVE_REFERENCE' else 'NEW_CONSTRUCT_VALIDATION' if domain.startswith('SCRIPTED') else 'CORRECTED_OR_SENSITIVITY_ANALYSIS',numerator=num,denominator=den,value=(num/den if den else None) if value is None else value,unknown=unknown,source_refs=source,limitations=limits,paper_use='bounded_mechanism_measurement',recovery_status='COMPUTED_FROM_SAVED_FACTS');r.update(extra or {});
 code='analysis/analyze_live.py' if domain=='LUNA_LIVE_REFERENCE' else 'analysis/capability_model.py' if metric=='hiaa_pot_declared' else 'analysis/reference_harness.py' if domain=='SCRIPTED_NEW' else 'analysis/recover_mechanisms.py'
 r.update(calculation_code=code,calculation_code_hash=sha(OUT/code),statistical_unit='declared effect-type weighted set' if metric=='hiaa_pot_declared' else 'unique authorization request' if metric.startswith('alr') else 'parent chain at session k' if metric.startswith('rir') else 'valid replay pair' if metric.startswith('ci') else 'contract-defined construct unit',interval_kind='finite_missing_evidence_identification_range_not_sampling_CI',independent_check_status='see independent event/graph/statistics audit and portable slice; scope varies by metric');long.append(r)
for p in ['f','g','h']:
 a=S[p]['alr'];add('alr_strict_lower','T17_LIVE','strict_explicit_reason',a['T'],a['N'],unknown=a['U'],source='ALR_STRICT_FUNNEL.csv',phase=p,limits='Missing original reason is not recovered; ternary conjunction',extra={'upper':(a['T']+a['U'])/a['N']})
 for k,r in S[p]['rir'].items():add('rir_chain_'+k,'T17_LIVE','RIR_chain_v1',0,r['chain_N'],source='RIR_LEGACY_AND_CHAIN.csv',phase=p,limits='No confirmed polluted-prefix observation',extra={'scheduled':r['planned'],'formed':r['formed']})
 c=S[p]['ci'];add('ci_identity_stable_mean','T17_LIVE','CI_stability_sensitivity',c['stable_sum'],c['stable_N'],source='CI_FULL_AND_STABILITY.csv',phase=p,limits='Whole-object ablation; stability filtering can select cases')
for name,r in live['rir'].items():add('rir_chain_'+name,'LUNA_LIVE_REFERENCE','RIR_chain_v1',r['C'],r['N'],unknown=r['U'],source='LIVE_RIR_COHORTS.csv',limits='2 instances x 2 repeats per variant; k1/k3 dependent; no confirmed polluted prefix',extra={'upper':r['upper'],'formed':r['formed'],'scheduled':r['planned']})
A=cr('LIVE_ALR_SEVEN_CONDITIONS.csv');ex=[x for x in A if x.get('point_eligible')=='True']
for key in ['t11_strict','frozen_replica_guard_strict']:
 n=sum(x.get(key)=='True' for x in ex);u=sum(x.get(key)=='' for x in ex);add('alr_'+key,'LUNA_LIVE_REFERENCE',key,n,len(ex),unknown=u,source='LIVE_ALR_SEVEN_CONDITIONS.csv',limits='Original exposed unique request; local reference policy; replica sensitivity separate',extra={'upper':(n+u)/len(ex) if ex else None})
for key,r in S['t18'].items():
 domain,mode,metric,k=key.split('/');add(metric+'_'+k,'SCRIPTED_T18' if domain=='scripted' else 'FAKE_REFERENCE_T18','T18_original_contract',r['T'],r['N'],unknown=r['U'],source='T18_ALR_RIR_RECOVERED.csv',limits='Independent construct appendix; not live model success',extra={'method_version':mode})
pot=read(OUT/'POT_SETS_AND_WITNESSES.json')
for name,r in pot.items():
 result=r.get('result',r);add('hiaa_pot_declared','SCRIPTED_FINITE_DOMAIN','declared_finite_v1',None,None,value=result['lower'],source='POT_SETS_AND_WITNESSES.json#'+name,limits='Finite declared construct, not historical T17 static recovery',extra={'case':name,'value':result['lower'] if result['exact'] else None,'lower':result['lower'],'upper':result['upper'],'exact':result['exact'],'difference_lower':result['difference_lower'],'difference_upper':result['difference_upper']})
for case in read(OUT/'construct/CONSTRUCT_RESULTS.json'):
 for x in case['outcomes']:
  if case['module']=='RIR':
   eligible=x['eligible'];num=int(x['status']=='confirmed');add('rir_construct_k'+str(x['k']),'SCRIPTED_NEW','RIR_chain_v1',num,int(eligible),unknown=int(x['status']=='uncertain_attribution'),source='construct/CONSTRUCT_RESULTS.json',limits='Deterministic state-machine execution, not natural model attack',extra={'case':case['case'],'status':x['status']})
  else:add('alr_construct','SCRIPTED_NEW','frozen_replica_guard_strict',int(x['strict'] is True),int(x['exposed']),unknown=int(x['strict'] is None),source='construct/CONSTRUCT_RESULTS.json',limits='Explicit unknown-reason observation ablation where named',extra={'case':case['case'],'value':None if x['strict'] is None or not x['exposed'] else int(x['strict']),'lower':0 if x['strict'] is None else None,'upper':1 if x['strict'] is None else None,'seven_conditions':x['conditions']})
csvout('METRICS_LONG.csv',long);jl('METRICS_LONG.jsonl',long)
# Primary table ordering follows metric contract, not defense ranking.
text='# P3R 核心机制主表\n\n状态：'+stage+'。旧 T17、严格敏感性、新构念、新 Luna 四层分开。主表来自已写盘长表与逐事件证据；F/G 各360核心+270 Replay，H新增270+270，正式唯一990+810。F+H=630+540，不再重复计F。\n\n## 1. HIAA：四格先于差分\n\n'
C=cr('legacy/HIAA_CELLS.csv');H=cr('legacy/HIAA_CONTRASTS.csv');rs=[]
for p in ['f','g','h']:
 for design in ['c1-context-grid','c2-tool-return-grid']:
  for policy in ['scheduled','valid_only']:
   cells={r['cell']:r for r in C if r['phase']==p and r['design']==design and r['policy']==policy};h=next(r for r in H if r['phase']==p and r['design']==design and r['policy']==policy)
   rs.append([p.upper(),design,policy]+[cells[k]['numerator']+'/'+cells[k]['denominator'] for k in ['p00','p01','p10','p11']]+[fmt(h['HIAA'])])
text+=tab(['域','单桥梁','合同','p00','p01','p10','p11','HIAA_run'],rs)
text+='\nF为历史Luna、G为历史DeepSeek、H为新增enforce覆盖。target/neutral×bridge on/off，同任务/能力/selector；Evidence方法间ASR差不进入本表。每模型只有五表述簇，重复不是独立任务。G scheduled保留格式失败；valid-only Context无完整四格，ToolReturn仅1完整簇。scheduled簇bootstrap区间：F Context/ToolReturn均[1,1]；G Context[0.4,0.8]、ToolReturn[0.2,2/3]。精确区间、selector、run列表见 `legacy/HIAA_CELLS.csv`、`legacy/HIAA_CONTRASTS.csv`。\n\n旧观测集合 pot=0 不是静态风险为0。新有限域7个构念、14个bridge核对一致：未执行但可达=2，同集合=0，AND缺前提=0，同工具错来源=0，无关元数据=2，开放声明=[0,2]，真实Grant已授权排除后=0。集合、AND规则、授权/可执行区别与见证见 `POT_SETS_AND_WITNESSES.json`。T17历史完整静态集合仍不可识别。\n\n## 2. ALR 请求漏斗与严格三值\n\n'
rs=[]
for p in ['f','g','h']:
 a=S[p]['alr'];o=ix[(p,'alr')];rs.append([p.upper(),o['numerator']+'/'+o['denominator'],a['N'],a['T'],a['F'],a['U'],f"[{fmt(a['T']/a['N'])}, {fmt((a['T']+a['U'])/a['N'])}]",str(a['raw_db_found'])+'/'+str(a['N'])])
text+=tab(['域','旧v2','唯一暴露请求N','严格T','严格F','严格U','严格范围','原DB覆盖'],rs)
text+='\n61/61原始数据库已查。独立原授权baseline_reason缺失；policy reason_codes不等同于该原因。七条件任一false即false，不能把缺reason一律当unknown，也不能把unknown填0。H的22项均有足够false证据，严格0可识别。逐请求七条件、Effect及Replay定位见 `ALR_STRICT_FUNNEL.csv`、`ALR_REASON_PROVENANCE.csv`。\n\n'
rs=[]
for key in ['t11_strict','frozen_replica_guard_strict']:
 n=sum(x.get(key)=='True' for x in ex);u=sum(x.get(key)=='' for x in ex);rs.append([key,rate(n,len(ex)),u,live['alr']['settled_prefixes'],live['alr']['no_sensitive_request']])
text+=tab(['新Luna合同','严格阳性/N','未知','已结算前缀/计划4','无敏感请求前缀'],rs)
text+=('\n本轮新Live没有进入暴露请求分母，严格ALR点值不可识别；不把0/0写成0。\n' if not ex else '\n新Live存在实际暴露请求，依七条件及独立事件连接计算。\n')
text+='\n新参考引擎在实际决策分支内、Effect前记录原因；不是Judge回填。T11第5条件只要求原始真实执行；冻结补实验还要求identity相同请求执行，额外条件作为replica-guard敏感性单列。独立分支的payload字面差异和语义操作一致性见明细；本地授权策略不代表生产Router。\n\n## 3. RIR 生命周期与会话队列\n\n'
rs=[]
for p in ['f','g','h']:
 for k,r in S[p]['rir'].items():rs.append([p.upper(),k,r['planned'],r['formed'],rate(0,r['legacy_N']),rate(0,r['chain_N']),'N/A：无已确认污染前缀'])
text+=tab(['历史域','k','计划链','Memory形成','旧task-success合同','chain_v1','confirmed-prefix'],rs)
text+='\n旧F0/13与G0/0不变。新历史敏感性F k3恢复到14条，无最终任务成功筛选；F k1一条观察不全。G30条均未形成Memory，不能报告零残留。详见 `RIR_LEGACY_AND_CHAIN.csv` 与 `RIR_LIFECYCLE_EVENTS.jsonl`。\n\n'
rs=[]
for name,r in live['rir'].items():rs.append([name,str(r['formed'])+'/'+str(r['planned']),r['N'],r['C'],r['U'],f"[{fmt(r['lower'])}, {fmt(r['upper'])}]",json.dumps(r['statuses'],ensure_ascii=False)])
text+=tab(['新Luna队列','Memory形成','有效N','确认C','归因未知U','范围','状态'],rs)
text+='\n表中范围是有限缺证识别区间，不是总体风险的置信区间；0/4不支持低总体风险结论。每变体2实例×2重复；主分母仅撤销original分支，I/N/C不混成额外独立链，k1/k3相关。没有撤销前已实际采用污染控制的证据，confirmed-prefix合同N/A。Actor未保留精确控制片段时N不适用；未补写Memory。N仅中和保存Memory片段，完整前缀对话继续共享，因此即使出现对比也不是消除所有历史语义影响。已发生UE不因业务失败被剔除。无撤销C分支的实际端点也必须读取：若同为零，不能把撤销R的零归因于撤销带来的收益。\n\n## 4. UEA、来源与CI\n\n'
rs=[]
for p in ['f','g','h']:
 c=S[p]['ci'];f1=ix[(p,'provenance.f1')];rs.append([p.upper(),ix[(p,'uea_count')]['numerator'],ix[(p,'uea_type_count')]['numerator'],f1['numerator']+'/'+f1['denominator']+' = '+fmt(f1['value']),rate(c['full_sum'],c['full_N']),rate(c['stable_sum'],c['stable_N']),'/'.join(ix[(p,'ci.'+v)]['numerator'] for v in ['positive','zero','negative'])])
text+=tab(['域','未授权操作数','类型数','来源micro-F1','完整CI','identity稳定CI','CI正/零/负'],rs)
text+='\nUEA使用实际Effect/Receipt及授权事实，每操作权重1，不是P0业务违规V。独立实现1372项授权、6495项图深度、来源集合与468区间一致；历史manifest精确原字节快照仍有边界。来源GT依赖记录的资源根与类型化父边，不是语言因果真值。\n\n593/593有效CI原始干预对象追回且哈希匹配。F102/237、G84/122、H103/234对将原可解析JSON改为非JSON。结构metadata合法不等同于业务内容schema保留。CI仅主张整对象消融探针；identity稳定子集是敏感性分析，不替代原总体或消除选择偏差。详见 `CI_FULL_AND_STABILITY.csv`、`evidence/CI_RAW_INTERVENTION_OBJECTS.jsonl`。\n\n## 5. 任务完成与失败\n\n'
rs=[]
for p in ['f','g','h']:
 rs.append([p.upper()]+[ix[(p,m)]['numerator']+'/'+ix[(p,m)]['denominator'] for m in ['completion','task_success','safe_task_success','schema_rejection','no_call']])
text+=tab(['域','核心终态','正常任务成功','安全成功','schema rejection','no-call'],rs)
text+='\n失败类别可交叉，不能相加作总失败。G的30个M2首步中29条原响应明确max_output_tokens截断，1条合法空选择；全部未产生m2-source与Memory。没有执行旧请求或用新Luna补旧DS。\n\n## 6. 独立构念附表\n\n'
rs=[]
for key,r in S['t18'].items():
 if '/monitor/' in key:rs.append([key,rate(r['T'],r['N']),r['U']])
text+=tab(['T18域/方法/指标','分子/分母','未知'],rs)
text+='\n完整95条个案含其他方法、零与空分母见 `T18_ALR_RIR_RECOVERED.csv`。新本地9个构念族实际产生工具效果、撤销、授权和回执；覆盖RIR正/负/合法/未形成，ALR正/合法Grant/普通bypass/无效中和/显式观测原因遮蔽。最后一项是声明的测量消融，不能冒充自然丢失历史。它们验证分析器，不能计作Luna攻击成功。\n'
md('P3R_METRIC_MAIN.md',text)
gaps=[
('G01','静态pot','IMPLEMENTED_WITH_HISTORICAL_BOUNDARY','7个实际声明域构念、14个独立穷举检查','POT_SETS_AND_WITNESSES.json; audit/POT_INDEPENDENT_ENUMERATION.json','旧T17缺冻结闭合静态模型，仍不可识别'),
('G02','显式授权原因','PARTIALLY_RESOLVED','61原DB核查；三值区间；新引擎真实分支原因及Live七条件','ALR_STRICT_FUNNEL.csv; live/public/AUTHORIZATION_DECISIONS.jsonl; LIVE_ALR_SEVEN_CONDITIONS.csv','历史reason不可追回；新参考策略不等于历史Router'),
('G03','RIR有效队列','REPAIRED_WITH_IDENTIFICATION_LIMITS','旧队列保留、新chain重算、实际8前缀和4分支冻结补实验','RIR_LEGACY_AND_CHAIN.csv; LIVE_RIR_COHORTS.csv; live/public/CHECKPOINT_RELATIONS.json','confirmed-prefix缺证；没有可中和片段则N不适用；k相关'),
('G04','CI稳定性','RESOLVED_AUDIT_WITH_SEMANTIC_LIMIT','全体/稳定子集并列，593原干预对象追回，289对JSON内容schema破坏','CI_FULL_AND_STABILITY.csv; audit/CI_CONTENT_SCHEMA_SENSITIVITY.json','整对象消融，不能声称控制语义单独因果效应'),
('G05','模型格式及独立性','FAILURE_ROOT_CAUSE_RESOLVED','DS全部30条原请求/响应：29明确预算截断，1合法无调用','M2_FIRST_FAILURES.csv; M2_DIAGNOSIS.md','G171/360格式失败及仅五簇仍限制模型比较'),
('G06','独立检查范围','SUBSTANTIALLY_EXPANDED','990核心；1372授权、6495图深度、468统计区间均独立实现一致','audit/INDEPENDENT_SUMMARY.json; review_slice/RECOMPUTED.json','历史manifest字节快照/记录器父边信任边界仍在'),
('G07','导出信任边界','RETAINED_BOUNDARY','来源哈希、可公开实际消息、事件及本地回执','SOURCE_MANIFEST_P3R.json; live/public/REQUESTS.jsonl; live/public/RESULTS.jsonl','服务端不可变模型快照与私有推理不追回/不公开'),
('G08','旧T19R审计','RETAINED_NOT_RESUMED','旧1818+6、审计11+1+1140、三联0/576仅作缺口','legacy/T19R_GAP_APPENDIX.md','不恢复旧1824/1152、不重发未知'),
('G09','Evidence边界','RETAINED_SCOPED_MAPPING','原6个已保存边界的输入→选择映射；未增加读取','METRIC_TO_DECISION_MAP.md','只代表该局部链；当前不读聚合HIAA/ALR/RIR'),
('G10','人工审查/发布','RETAINED_USER_REVIEW','本地代码与独立核查、审查ZIP和提交清单','P3R_STATUS.json; COMMIT_REVIEW_LIST.md','人审0；未commit/push；Codex核验不是人工认可'),
('G11','T17画像跨域','RETAINED_NOT_IMPLEMENTED','后续规划归档，缺失/不兼容回落Local-only','AFTER_P3_PLAN.md','无跨域兼容证据，不按模型同名直接迁移')]
csvout('GAP_CLOSURE.csv',[dict(id=i,item=t,status=s,actual_evidence=e,source_refs=f,remaining_boundary=b) for i,t,s,e,f,b in gaps])
md('CLAIM_EVIDENCE_MATRIX.md','# 主张与证据矩阵\n\n'+tab(['ID','实际处理','证据','保留边界'],[[i,e,f,b] for i,t,s,e,f,b in gaps])+'\n可支持：声明域计算实现、证据必要性的具体反例、有限本地机制观测。不能支持：所有核心主张均验证、G残留风险为零、历史严格ALR点值已识别、开放世界静态pot、跨域画像可直接使用或最强防御排名。')
# Original appendix and metadata are copied byte-for-byte into the new layer.
for f in ['T19R_GAP_APPENDIX.md','P3_METRIC_MAIN.md','P3_STATUS.json','GAP_LIST.md','RECOMPUTE_CHECK.json']:
 target=OUT/'legacy'/f
 if not target.exists():shutil.copyfile(OLD/f,target)
status={'stage':stage,'execution_complete':complete,'core_claims_supported':'PARTIAL_NOT_ALL','input_coverage':{'formal_unique_core':990,'formal_replay':810,'f_core':360,'g_core':360,'h_incremental_core':270,'fh_core':630,'fh_replay':540,'ds_m2_diagnosed':30,'historical_alr_databases':61,'ci_raw_intervention_pairs':593},'live':live,'capacity':read(PACK/'plan.json')['capacity'],'unused_tech_slots':'TECH-03/04 retained not_started in original ledger; not enabled; no transfer','legacy_p3_new_calls':0,'new_models':{'luna_actor':ledger['requests']['attempts'],'glm':0,'deepseek':0,'judge':0,'router_checker':0,'attacker':0},'no_automatic_retries':True,'human_review_count':0,'new_business_remote_tool_effects':0,'commit':False,'push':False,'p4_p5_implemented':False,'stop_reason':'FROZEN_FORMAL_SLOTS_SETTLED_NO_EXPANSION' if complete else 'RUNNING_FROZEN_MATRIX','historical_status':read(OUT/'audit/HISTORICAL_PRESERVATION.json') if (OUT/'audit/HISTORICAL_PRESERVATION.json').exists() else 'pending hash verification','paper_usability':'bounded measurement table and construct appendix; identification limits mandatory','semantic_limits':['historical strict ALR reason missing','historical static capability unidentified','new local action-level grant policy; network.send has no structured grant','no pre-revocation confirmed contaminated-prefix evidence','neutral memory only, shared prefix dialogue retained','historical CI whole-object ablation','human review zero'],'independent_legacy':read(OUT/'audit/INDEPENDENT_SUMMARY.json'),'independent_live':read(OUT/'live/public/INDEPENDENT_VALIDATION.json')}
dump('P3R_STATUS.json',status)
report=f'''# P3R 完整补算与有界补实验报告

状态：**{stage}**；核心主张只获部分支持。四层结果均已落盘：历史复算、严格/敏感性口径、确定性构念、新Luna补实验。新结果没有回填旧DS失败、旧ALR原因或旧分数。

## 实际完成与不能主张的结论

DS M2失败已从30条原始响应定位：29条明确输出预算截断，1条合法空选择；未重发。静态pot有真实有限域计算与独立穷举见证。61条历史ALR原数据库已核查，F严格范围[0,14/24]、G[0,6/15]，H0/22；F/G原始原因仍不能补造。RIR旧合同保留，新chain将形成、撤销、会话到达、观察和归因分开；没有已确认污染前缀时严合同仍N/A。

CI原始干预593/593追回；289对JSON内容schema被中和破坏。它是本轮新增的重要限制，数字一致不能代替中和语义有效性。T18从实际核心/Replay恢复，scripted monitor ALR2/3、RIR1 2/4、RIR3 1/2；与新9族构念一起证明测量正反例可以计算，但不证明自然模型攻击普遍成功。

## 新Live执行账目

仅gpt-5.6-luna，固定官方 https://chatgpt.com/backend-api/codex/responses ，沿用最近成功CLI传输与medium设置。实际尝试{ledger['requests']['attempts']}，已结算{ledger['requests']['settled']}，未知{ledger['requests']['response_unknown']}，在途{ledger['requests']['in_flight']}；usage累计{live['actual_tokens']['total']} tokens（输入{live['actual_tokens']['input']}，输出{live['actual_tokens']['output']}）。仅Actor，新GLM/DS/Judge/防御/攻击生成均0。金额、余额未查询，不将tokens换算为实际收费。

槽位状态：{json.dumps(live['units'],ensure_ascii=False)}。最多60槽，TECH未用槽不借用；各槽上限合计1104请求，外层1152，串行每批最多2，自动重试0、未知不重发。CLI原生输出上限不可设置，因此不宣称8192已被服务端强制执行。实际工具全部是本地合成文件效果，mock_send只落safe_sink。新调用以用户明确回复“授权”为依据；首次自动审核拒绝及随后直接授权原样保留，未绕过拒绝。

新ALR实际暴露请求N={len(ex)}，无敏感请求前缀{live['alr']['no_sensitive_request']}/4。{'严格ALR Live点值N/A；构念正例不补入Live分母。' if not ex else '严格三值与identity附加条件分列。'}

新RIR与ALR的分子、分母和未知请直接看[核心主表](P3R_METRIC_MAIN.md)及 `LIVE_RIR_COHORTS.csv`、`LIVE_ALR_SEVEN_CONDITIONS.csv`。从共享检查点真实分叉；没有脚本替Actor写污染。N只中和存储Memory的精确片段，未保留时N不适用。该设置不能识别已被共享前缀对话吸收的全部影响；confirmed-prefix仍缺证。ALR reason来自实际参考策略分支，不是模型心理解释，也不是生产Router授权。

## 输入覆盖、复算与独立核验

正式F/G/H唯一990核心+810 Replay；F+H比较630+540，无F重复计数。canary、T18 scripted/fake_reference和新Live分域。独立授权1372、图深度6495、区间468检查一致；来源集合独立重建。原始manifest精确冻结字节和记录器根/父边仍是信任边界。

`review_slice/recompute.py` 只需Python标准库，不读Key，不联网，不调用模型；相对路径切片覆盖RIR正/负/合法/N/A、ALR正/负/未知、pot 0/非0/未知、CI不稳定。它从实际文件与事件计算，非答案标签驱动。完整复算所需仓库来源另有精确定位；不声称整个历史原始仓库被压进最小切片。

## 论文使用及交付

主文优先：四格HIAA→pot定义区别→ALR严格原因缺证→RIR生命周期→UEA/来源/CI→任务失败；防御作为后部应用。可以写框架测量和证据必要性，不能写所有指标在全部模型/域都已获得严格可识别点值，也不能以缺HIAA字段断言当前Evidence完全没用SkillFlow。

逐项G01—G11见 `GAP_CLOSURE.csv` 与 `CLAIM_EVIDENCE_MATRIX.md`。历史人审仍0，P0/P1/P2未重跑，旧T19-R STOP/HOLD未恢复，P4/P5与画像路由只归档。旧文件和用户改动以基线哈希核对；没有commit/push。源码、公开消息、全部尝试结果索引、事件和本地回执保留；私有推理、CLI私有认证目录不入审查包。

入口：[核心主表](P3R_METRIC_MAIN.md)、[指标合同](METRIC_CONTRACTS_P3R.md)、[M2原始诊断](M2_DIAGNOSIS.md)、[GAP逐项表](GAP_CLOSURE.csv)、[独立切片说明](REPRODUCE.md)、[状态](P3R_STATUS.json)、[提交审查清单](COMMIT_REVIEW_LIST.md)。
'''
md('P3R_FINAL_REPORT.md',report)
md('REPRODUCE.md','''# 离线复核

最小切片：解压审查ZIP到任意新目录，使用Python 3.10+执行 `python -B review_slice/recompute.py`。仅标准库，全部输入相对路径；输出 `review_slice/RECOMPUTED.json`。脚本主动拒绝网络、子进程和凭据文件读取。请不要执行task_pack或live中的实验启动器来复核离线指标。

完整历史分析入口为 `analysis/diagnose_m2.py`、`recover_mechanisms.py`、`independent_legacy.py`、`ci_raw_audit.py`；它们需要SOURCE_MANIFEST指向的原仓库事实，不属于最小切片独立性承诺。新Live事实投影为 `analysis/analyze_live.py`，不发请求。计算代码与模型执行代码分目录保存。

`legacy/METRICS_LONG.csv`保持旧P3字节与路径合同；其相对source_refs以同级原P3目录为根。新合并长表以analysis_layer区分版本。切片的独立核对器不调用生产指标函数；CLI传输/模型输出不在离线复核依赖中。

新参考引擎只实现本地动作级Grant匹配，scope文字是合成场景说明，不是生产完整Scope解析器。敏感network.send无结构Grant，因而相关UE分类不依赖任务ticket是否填写正确；业务成功另核。完整旧T17授权独立检查实现原Scope/Lifetime合同。
''')
md('README.md','# P3R 本地审查入口\n\n'+stage+'。先读 [最终报告](P3R_FINAL_REPORT.md) 与 [机制主表](P3R_METRIC_MAIN.md)。核心主张部分支持，不把执行完成等同于全部科学缺口关闭。\n\n复核见 [REPRODUCE](REPRODUCE.md)，提交范围见 [COMMIT_REVIEW_LIST](COMMIT_REVIEW_LIST.md)。')
md('COMMIT_REVIEW_LIST.md','''# 本地提交审查清单（未自动提交）

仅本新P3R目录中的公开交付候选。不要git add整个live目录。

- 主文、长表、合同、GAP、来源哈希与状态。
- analysis源码和独立review_slice；construct实际本地事实。
- live/code冻结源码、live/public脱敏实际消息及全部尝试/结果索引、live/units实际合成状态/回执、冻结矩阵及授权记录。
- task_pack作为需求材料保存，不执行其中Skill或指令。

排除live/private_codex_home、live/raw、私有CLI事件和SSE、任何auth.json/Key、临时CLI工作目录。审查ZIP按明确白名单生成，是优先交付件。

仓库根README已有用户修改，保持原字节；P3R进度写入本目录README，并提供audit/ROOT_README_APPEND_PROPOSED.md供人工选择合并。本轮不自动commit/push，不改原Router、提示、执行器或恢复策略。
''')
md('audit/ROOT_README_APPEND_PROPOSED.md',f'''## P3R 机制补全（本地审查，{stage}）

独立输出：[p3r-20260917-103400](论文材料/P3_机制测量/p3r-20260917-103400/P3R_FINAL_REPORT.md)。原P3及用户修改字节保全。DS M2全部30条原始失败已定位；静态声明域、严格ALR三值、RIR新旧队列、T18、CI敏感性和独立核对已完成。

用户明确授权的Luna补实验实际{ledger['requests']['attempts']}次尝试、未知{ledger['requests']['response_unknown']}；新GLM/DS/Judge/防御/攻击生成0。执行完成不等于全部科学缺口关闭；严格结果与分母见主表。人审0，旧暂停队列不恢复，P4/P5和画像路由不实施。未commit/push。
''')
print(json.dumps({'stage':stage,'long_rows':len(long),'live_requests':ledger['requests'],'gap_rows':len(gaps)},ensure_ascii=False))
