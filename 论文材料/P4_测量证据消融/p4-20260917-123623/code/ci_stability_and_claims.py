from common import *
from collections import Counter,defaultdict

guard();docs=rows(OUT/'minimal_data/BASE_DOCUMENTS.jsonl');units={d['id']:d for d in docs};qs={q['query_id']:q for q in rows(OUT/'minimal_data/PREDICTOR_QUERIES.jsonl')};reg={r['query_id']:r for r in rows(OUT/'QUERY_REGISTRY.jsonl')};parents={}
for d in docs:
 if d.get('layout')!='legacy':continue
 for p in d.get('counterfactual',[]):parents[digest(p)]=d
result=[]
for r in rows(OUT/'results/V00.jsonl'):
 if r['metric']!='CI' or r['protocol']!='legacy_object_ablation':continue
 q=qs[r['query_id']];d=units[q['unit']];p=d['counterfactual']['pair'];parent=parents.get(digest(p)) if p else None;original=None
 if parent:
  sel=p['selector'];ops=[x for x in parent['observation']['ops'] if x['action']==sel['action'] and (sel.get('source_pattern') is None or x['source']==sel['source_pattern']) and (sel.get('sink_pattern') is None or x['sink']==sel['sink_pattern'])];original=any(any(receipt['op']==x['id'] and receipt['effect_id']==x['effect_id'] for receipt in parent['receipt']['records']) for x in ops)
 i=r['details'].get('identity_endpoint');n=r['details'].get('neutral_endpoint');result.append(dict(query_id=r['query_id'],phase=reg[r['query_id']]['phase'],source_ref=reg[r['query_id']]['source_ref'],original_endpoint=original,identity_endpoint=i,neutral_endpoint=n,ci=r['value'],structural_eligible=r['eligibility'],original_identity_stable=None if original is None or i is None else original==i,semantic_preservation=r['details'].get('semantic_preservation'),interpretation='post-prediction Full-only descriptive sensitivity; no new query or execution'))
csvout('CI_ORIGINAL_IDENTITY_STABILITY.csv',result)
summary=[]
for phase in ['f','g','h']:
 for subset in ['all_structural','original_identity_stable']:
  rr=[r for r in result if r['phase']==phase and r['structural_eligible'] is True and (subset=='all_structural' or r['original_identity_stable'] is True)];summary.append(dict(phase=phase,subset=subset,denominator=len(rr),positive=sum(r['ci']==1 for r in rr),zero=sum(r['ci']==0 for r in rr),negative=sum(r['ci']==-1 for r in rr),mean=sum(r['ci'] for r in rr)/len(rr) if rr else None,semantic_valid_count=0))
csvout('CI_STABILITY_SUMMARY.csv',summary);print(canonical(summary))
claims=[{'claim':'证据家族影响机制测量可辨识性','support':'PARTIAL','evidence':'P4_METRIC_MAIN.csv;FULL_TO_VIEW_TRANSITIONS.csv','limit':'定义依赖不能推出框架独有必要性'}, {'claim':'存在有限域不可辨识见证','support':'YES_FINITE_ONLY','evidence':'IDENTIFIABILITY_WITNESSES.json','limit':'2对既有声明模型；不是新增Live样本'}, {'claim':'删证必然使全部结论未知','support':'REFUTED','evidence':'CASEBOOK.md;TASK_EVIDENCE_RECONSTRUCTION.csv','limit':'任务冗余和合取短路保留'}, {'claim':'Full等于gold/自然语言100%正确','support':'NOT_SUPPORTED','evidence':'GOLD_PROVENANCE.json;INDEPENDENT_REFERENCE_SCORES.csv','limit':'192个确定受控查询，Full判断190；人审0'}, {'claim':'旧CI精准语义有效','support':'NOT_SUPPORTED','evidence':'CI_DETAILS.csv;CI_STABILITY_SUMMARY.csv','limit':'289破坏JSON，304未知；稳定不是语义有效'}, {'claim':'新Live撤销产生因果安全收益','support':'NOT_SUPPORTED','evidence':'RIR_SESSION_COHORTS.csv','limit':'目标、中性、未撤销对照无风险；confirmed-prefix缺证'}];csvout('CLAIM_EVIDENCE_MATRIX.csv',claims)
