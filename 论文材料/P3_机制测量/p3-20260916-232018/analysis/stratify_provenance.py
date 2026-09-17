"""Mechanism/depth presentation strata, without changing original estimands."""
import ast,json,csv,collections,sys,os
from pathlib import Path
OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[2];READS=set()
for node in ast.parse((OUT/'analysis/independent.py').read_text('utf-8-sig')).body:
 if isinstance(node,ast.FunctionDef) and node.name in ('guard','dump','csvout'):exec(compile(ast.Module(body=[node],type_ignores=[]),'<io>','exec'))
sys.addaudithook(guard)
raw=[json.loads(x) for x in (OUT/'facts/PROVENANCE.jsonl').open(encoding='utf-8')];vectors=json.loads((OUT/'facts/FRESH_VECTORS.json').read_text('utf-8'));out=[]
for phase in vectors:
 rows=[x for x in raw if x['phase'] in ('f','h') and x['mode']==phase[3:]] if phase.startswith('fh_') else [x for x in raw if x['phase']==phase]
 def mechanism(r):
  c=r['condition'].lower()
  return 'Context' if c.startswith('c1-') else 'Tool Return' if c.startswith('c2-') else 'Memory' if c.startswith('m2-') else 'Other conditions'
 for domain in sorted({mechanism(x) for x in rows}):
  rs=[x for x in rows if mechanism(x)==domain];prev={}
  for depth in [None]+sorted({x['depth'] for x in rs}):
   ss=rs if depth is None else [x for x in rs if x['depth']==depth];tp=sum(x['tp'] for x in ss);fp=sum(x['fp'] for x in ss);fn=sum(x['fn'] for x in ss);r=tp/(tp+fn) if tp+fn else None;previous=prev.get(depth-1) if depth is not None else None
   out.append({'phase':phase,'mechanism_condition_stratum':domain,'depth':depth,'artifacts':len(ss),'tp':tp,'fp':fp,'fn':fn,'precision':tp/(tp+fp) if tp+fp else None,'recall':r,'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,'decay':previous-r if previous is not None and r is not None else None,'formula':'Recall(depth-1)-Recall(depth)','source':'facts/PROVENANCE.jsonl; filter phase/mode/condition/depth','limitation':'condition-based mechanism stratum; depth from fresh production graph; not each edge boundary causal category'})
   if depth is not None:prev[depth]=r
 total=[x for x in out if x['phase']==phase and x['depth'] is None]
 for key in ('tp','fp','fn'):assert sum(x[key] for x in total)==vectors[phase]['provenance.'+key]['value']
csvout('tables/PROVENANCE_BY_MECHANISM_AND_DEPTH.csv',out)
p=OUT/'P3_METRIC_MAIN.md';s=p.read_text('utf-8');s=s.replace('[来源逐 Artifact](tables/PROVENANCE_DETAILS.csv)', '[来源逐 Artifact](tables/PROVENANCE_DETAILS.csv)、[Context/Tool Return/Memory 与深度分层](tables/PROVENANCE_BY_MECHANISM_AND_DEPTH.csv)');s=s.replace('[漏斗](tables/ALR_AGGREGATES.csv)','[漏斗](tables/ALR_AGGREGATES.csv)、[全部请求→敏感请求→声明暴露](tables/ALR_REQUEST_POPULATIONS.csv)');p.write_text(s,encoding='utf-8')
dump('audit/MECHANISM_STRATA_CHECK.json',{'group_rows':len(out),'aggregate_tp_fp_fn_matches_original_all_seven_populations':True,'new_calls':0})
print('mechanism/depth rows',len(out))
