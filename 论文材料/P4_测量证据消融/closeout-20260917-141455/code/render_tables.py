"""Render all editorial tables from one frozen closeout_data.json. No original predictor imports."""
from common import *
from collections import Counter

def fmt(v):
 if v is None or v=='':return 'N/A'
 if isinstance(v,float):return f'{v:.6g}'
 if isinstance(v,(list,dict)):return can(v)
 return str(v)
def md(headers,rows_):return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(fmt(v).replace('|','/').replace('\n',' ') for v in r)+' |' for r in rows_])
def texescape(s):
 return ''.join({'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}.get(c,c) for c in fmt(s))
def latex(caption,headers,rr):
 return '% UTF-8 snippet; requires longtable and a Chinese-capable LaTeX setup.\n'+r'\begin{longtable}{'+'l'*len(headers)+'}\n'+r'\caption{'+texescape(caption)+'}'+r'\\'+'\n'+r'\hline'+'\n'+' & '.join(map(texescape,headers))+r' \\'+'\n'+r'\hline\endhead'+'\n'+'\n'.join(' & '.join(map(texescape,r))+r' \\' for r in rr)+'\n'+r'\hline\end{longtable}'+'\n'
def result_text(r):
 if r.get('cells'):return '; '.join(k+':'+str(v['numerator'])+'/'+str(v['denominator']) for k,v in r['cells'].items())+'; D='+fmt(r['value'])
 if r.get('value') is not None:return fmt(r['value'])
 if r.get('lower') is not None and r.get('upper') is not None:return '['+fmt(r['lower'])+','+fmt(r['upper'])+']'
 return 'N/A ('+r['status']+')'

def main():
 guard();d=read(OUT/'data/closeout_data.json');a=[dict(row_id=f'A{i:03}',**r) for i,r in enumerate(d['table_A'],1)];b=[dict(row_id=f'B{i:03}',**r) for i,r in enumerate(d['table_B'],1)];c=[dict(row_id=f'C{i:03}',**r) for i,r in enumerate(d['table_C'],1)];sources=[]
 for rr in [a,b,c]:
  for r in rr:sources.append(dict(row_id=r['row_id'],source_ref=r['source_ref'],source_sha256=r.get('source_sha256'),contract=r.get('contract') or r['protocol'],unit=r['unit'],boundary=r['boundary']))
 csvout('tables/mechanism_results.csv',a);csvout('tables/metric_ablation.csv',b);csvout('tables/metric_ablation_all13_strata.csv',d['table_B_full_strata']);csvout('tables/self_vs_downstream.csv',d['self_vs_downstream']);csvout('tables/independent_reference.csv',c);csvout('tables/independent_reference_overall.csv',d['table_C_overall']);csvout('tables/SOURCE_LOCATORS.csv',sources);csvout('NUMERIC_CONFLICTS.csv',d['conflicts'])
 ar=[[r['row_id'],r['execution_domain']+'/'+str(r['phase']),r['display_metric'],r['contract'],r['design'],r['unit'],str(r['numerator'])+'/'+str(r['denominator']) if r['denominator'] is not None else 'see cells/set',result_text(r),r['status']] for r in a]
 br=[[r['row_id'],r['display_metric'],r['protocol']+'/k'+str(r['horizon']),r['view_id'],r['fixed_queries'],r['point'],r['bounded'],r['unknown'],r['not_applicable'],r['eligible_unknown']] for r in b]
 cr=[[r['row_id'],r['domain'],r['display_metric'],r['protocol'],r['view_id'],r['reference_queries'],r['determinate_applicable_truths'],r['answered'],r['agrees'],r['wrong_determinate'],r['judgment_coverage'],r['answered_agreement']] for r in c]
 oh=['视图','参考查询','资格已知','确定适用真值','已答/真值','已答一致/已答','覆盖','错误确定数'];orr=[[r['view_id'],r['reference_queries'],r['eligibility_known'],r['determinate_applicable_truths'],f"{r['answered']}/{r['determinate_applicable_truths']}",f"{r['agrees']}/{r['answered']}",r['judgment_coverage'],r['wrong_determinate']] for r in d['table_C_overall']]
 specs=[('A','机制实证摘要',['行','执行域/阶段','指标','原合同','设计','单位','分子/分母','值/四格','状态'],ar,'表A只整理已保存P3/P3R结果；严格合同的分层补充明确来自P4已保存Full表。历史Live、受控构念、T18和新Live不混池。bootstrap原字段完整保存在CSV中，缺证识别界另列。F/H ToolReturn valid_only的P3R分母13与P4分母15存在版本差异，见NUMERIC_CONFLICTS.csv；同为1不能互换分母。'),('B','P4 指标×证据视图',['行','显示指标','protocol/k','视图','固定N','点值','范围','未知','NA','资格未知'],br,'所有13视图保留；每指标/合同/k的固定N不变。点值包括布尔、数字和集合，不是风险率。状态满足N=P+B+U+NA+conflict+analysis_error；当前后两项均0。资格未知是未知的子集，不再加总。域、study、phase、source_variant、branch完整4758层见metric_ablation_all13_strata.csv。单位及边界逐行见SOURCE_LOCATORS.csv。'),('C','独立构念参照',['行','参照域','显示指标','合同','视图','参考N','真值N','已答','一致','错答','覆盖','已答一致率'],cr,'314为参考查询总数，308为资格已知，192为确定且适用真值。覆盖=已答/192或该行真值N；已答一致率=一致/已答，零已答为空。指标、合同、分支与k相关，不能当独立实验。自然语言人审0。')]
 combined=['# P3/P4论文表（统一整理数据生成）','', '三种格式共同来自[data/closeout_data.json](data/closeout_data.json)。完整源文件、合同、统计单位与适用边界按行ID见[tables/SOURCE_LOCATORS.csv](tables/SOURCE_LOCATORS.csv)。原预测及标签未修改。'];latexall=[]
 for label,title,headers,rr,note in specs:
  text='# 表'+label+'：'+title+'\n\n'+note+'\n\n'+md(headers,rr)+'\n\n各行source与适用边界见同目录SOURCE_LOCATORS.csv；禁止把未知或空分母置零。\n';(OUT/f'tables/table_{label}.md').write_text(text,encoding='utf-8');lt=latex('表'+label+'：'+title,headers,rr);(OUT/f'tables/table_{label}.tex').write_text(lt,encoding='utf-8');latexall.append(lt);combined+=['',f'## 表{label}：{title}',note,'',md(headers,rr)]
 combined+=['','## 表C总体（13视图）','',md(oh,orr),'','## 自身与下游影响','', '固定的命名关系将来源成员、CI、任务完成、失败细类、声明能力分别视为对应证据家族的自身估计量。无独立Receipt/Grant/reason指标的依赖列为downstream；它是解释分组，不是新评分。全部关系、分母和状态转移见[tables/self_vs_downstream.csv](tables/self_vs_downstream.csv)。','',md(['来源删证后的点值损失','查询数','关系'],[['Provenance',d['source_decomposition']['Provenance'],'self'],['ALR',d['source_decomposition']['ALR'],'downstream'],['CI',d['source_decomposition']['CI'],'downstream'],['RIR',d['source_decomposition']['RIR'],'downstream']])];(OUT/'PAPER_TABLES.md').write_text('\n'.join(combined)+'\n',encoding='utf-8');latexall.append(latex('表C总体',oh,orr));(OUT/'tables/paper_tables.tex').write_text('\n'.join(latexall),encoding='utf-8')
 # Display aliases only. Original metric and protocol remain part of every table key.
 aliases=[]
 for metric,protocol in sorted({(r['raw_metric'],r['protocol']) for r in b}):
  name=display(metric)
  if metric=='ALR':name='ALR—显式reason原七条件' if protocol=='T11_explicit_reason' else 'ALR—附加identity执行门'
  if metric=='HIAA_pot_observed':name='观测未授权效果集合差'
  if metric=='HIAA_pot_declared':name='声明有限域可达能力差'
  if metric=='CI':name='旧整对象消融有符号差' if protocol=='legacy_object_ablation' else '精准控制语义资格检查'
  aliases.append(dict(study='P4',raw_metric=metric,protocol=protocol,display_metric=name,definition='U AND NOT receipted risk-selector endpoint' if metric=='E_STS' else 'retain exact original metric contract',unit=next(r['unit'] for r in b if r['raw_metric']==metric),boundary='display only; no renamed source field or new score; UEA authorization differs from target endpoint',source_ref='../p4-20260917-123623/METRIC_CONTRACTS.csv'))
 aliases+=[dict(study='P0',raw_metric='E_STS',protocol='NOT_IMPORTED_P0_CONTRACT',display_metric='E_STS_posthoc(P0)',definition='auxiliary task success with absence of actual business violation V under P0 annotation contract; explanatory mapping only; native P0 protocol not imported',unit='historical observation under P0 contract',boundary='not receipt/Grant gold; human review remains 0; no relabeling or pooling with P4',source_ref='task_pack/SkillFlow_P4_Closeout_Codex/02_CLOSEOUT_SPEC.md#4'),dict(study='T17',raw_metric='alr',protocol='T17-v2_derived_reason_legacy',display_metric='ALR—历史推导reason版本',definition='preserve archived point values 14/24 and 6/15',unit='unique exposed authorization request',boundary='not replaceable with either strict identification range',source_ref='../../P3_机制测量/p3r-20260917-103400/METRIC_CONTRACTS_P3R.md')]
 csvout('METRIC_NAME_MAP.csv',aliases)
 # Six cards use only saved predictions/witnesses plus one original saved binding snippet.
 cp=d['cases']['selected_predictions'];cards=[]
 for i,w in enumerate(d['cases']['witnesses'],1):
  qa,qb=w['query_a'],w['query_b'];vid=w['view_id'];cards.append(dict(card=f'W{i}',title='有限不可辨识见证：'+vid,queries=[qa,qb],objects=[cp[qa]['V00']['registry']['native_unit_ref'],cp[qb]['V00']['registry']['native_unit_ref']],view=vid,visible='两模型删证后许可文档相同，仅以一致不透明身份双射对齐；许可文档哈希 '+w['visible_hash'],masked=FAMILIES[vid],before=[cp[qa]['V00'],cp[qb]['V00']],after=[cp[qa][vid],cp[qb][vid]],independent_reference={'truths':[w['truth_a'],w['truth_b']],'logic':w['independent_reference'],'source':d['cases']['witness_source']+f'#/{i-1}'},conclusion='在该有限观察限制内，只用相同观察的估计器无法保证对两个不同真值都给出正确点值；不证明框架唯一。'))
 tc=d['cases']['task'];qid=tc['query_id'];binding=read(OUT/'data/case_evidence_bindings.json')[0];cards.append(dict(card='R1',title='任务证书可替代',queries=[qid],objects=[a['object_id'] for a in binding['certificate']['artifacts']],view='V05',visible={'required_obligations':binding['observation']['task_obligations'],'original_objects':binding['observation']['objects'],'object_sessions':binding['lifecycle']['object_sessions']},masked='task_success_evidence certificate bindings',before=[cp[qid]['V00']],after=[cp[qid]['V05']],independent_reference={'basis':'原对象哈希、公开机械义务和session事实是证书以外的路径；本历史查询不在192条有限参照真值集合内，不伪称外部gold','source':binding['source_ref'],'sha256':binding['sha256']},conclusion='该查询保留原点值；1059/1059是既有同类点值重建覆盖，不是新增独立任务。'))
 sc=d['cases']['short_circuit'];qid=sc['query_id'];cards.append(dict(card='S1',title='合法false短路',queries=[qid],objects=[cp[qid]['V00']['registry']['native_unit_ref']],view='V08',visible='真实Grant仍可见；原七条件第一项“无有效Grant”为false',masked='original decision reason',before=[cp[qid]['V00']],after=[cp[qid]['V08']],independent_reference=cp[qid]['V00']['gold'],conclusion='合取已有false足以保持false；缺reason不强制所有结果unknown。'))
 qid=d['cases']['hiaa_query'];cards.append(dict(card='I1',title='F/Context scheduled：点值变识别范围',queries=[qid],objects=['c1-context-grid','p00','p01','p10','p11'],view='V01',visible='请求、selector、target/neutral与bridge四格和原计划分母仍可见；缺同请求Receipt',masked='Receipt',before=[cp[qid]['V00']],after=[cp[qid]['V01']],independent_reference={'basis':'既有四格和已记录区间的算术核对；不在192条受控真值集合内，不用Full作gold','source':'../p4-20260917-123623/checks/INDEPENDENT_RECOMPUTE.json'},conclusion='Full=1；删Receipt后[-1,1]，p01与p11各15个执行命题未知，p00/p10仍为0。识别范围不是概率范围或bootstrap区间。'))
 qq=d['cases']['unknown_reason_queries'];cards.append(dict(card='U1',title='Full因缺原reason仍未知',queries=qq,objects=['unknown_reason-alr-original'],view='V00/V08',visible='已有请求、实际执行、claim依据与中和对；许可原reason为空',masked='既有测量切片本来就缺原reason，Full也不补造',before=[cp[q]['V00'] for q in qq],after=[cp[q]['V08'] for q in qq],independent_reference=[cp[q]['V00']['gold'] for q in qq],conclusion='同一个构念的两个ALR合同：独立参照true、Full均unknown；不是两个独立实验；不得把独立参照保有的原因回填许可视图。这是既有受控遮蔽，不是自然历史遗失。'))
 dump('data/paper_cases.json',cards);ct=['# 六张已有案例卡','本轮无新增构念或语义判分。下列“before/after”均为已保存预测；独立参照有无覆盖明确区分。']
 def pr(x):
  p=x['prediction'];return f"{p['query_id']}: {p['status']}, eligibility={p['eligibility']}, value={p['value']}, bounds=[{p['lower']},{p['upper']}]"
 for c0 in cards:
  ct+=['',f"## {c0['card']} {c0['title']}",f"查询/对象：`{'; '.join(c0['queries'])}`；`{'; '.join(c0['objects'])}`。",'许可信息：'+fmt(c0['visible'])+'。','遮蔽：'+c0['masked']+'。','之前：'+ '; '.join(pr(x) for x in c0['before'])+'。','之后：'+ '; '.join(pr(x) for x in c0['after'])+'。','独立参照依据：'+fmt(c0['independent_reference'])+'。',c0['conclusion'],'最小源定位：'+'；'.join(x['source_ref']+' / SHA256 '+x['source_sha256'] for x in c0['before']+c0['after'])+'。','许可读取/合同证明：'+fmt(c0['after'][0]['prediction']['used_evidence'])+'。']
 (OUT/'PAPER_CASES.md').write_text('\n'.join(ct)+'\n',encoding='utf-8')
 dump('checks/RENDER_PROVENANCE.json',{'input':'data/closeout_data.json','input_sha256':sha(OUT/'data/closeout_data.json'),'table_rows':{'A':len(a),'B':len(b),'C':len(c)},'source_locator_rows':len(sources),'case_cards':len(cards),'all_formats_generated_by':'code/render_tables.py','latex_compiled':False,'pdf_not_required':True})
 print(can({'rendered_tables':{'A':len(a),'B':len(b),'C':len(c)},'cards':len(cards),'alias_rows':len(aliases)}))
if __name__=='__main__':main()
