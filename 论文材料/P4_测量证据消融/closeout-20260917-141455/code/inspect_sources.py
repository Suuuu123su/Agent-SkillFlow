from pathlib import Path
import json,csv,collections
O=Path(__file__).resolve().parents[1];R=O.parents[2];P=O.parent/'p4-20260917-123623';S=R/'论文材料/P3_机制测量/p3r-20260917-103400'
def csvs(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
for name in ['legacy/HIAA_CELLS.csv','legacy/HIAA_CONTRASTS.csv','RIR_LEGACY_AND_CHAIN.csv','LIVE_RIR_COHORTS.csv','LIVE_ALR_SEVEN_CONDITIONS.csv','CI_FULL_AND_STABILITY.csv']:
 a=csvs(S/name);print(name,'rows',len(a),'sample',json.dumps(a[:1],ensure_ascii=False)[:4500])
a=csvs(S/'METRICS_LONG.csv');print('layers',dict(collections.Counter(x['analysis_layer'] for x in a)));print('metrics',sorted({x['metric_id'] for x in a}));print('new rows',[{k:x[k] for k in ['study','phase','domain','model_config','metric_id','contract_version','population_id','unit','value','numerator','denominator','status','analysis_layer','case']} for x in a if x['analysis_layer']!='LEGACY_RECOMPUTED'][:35])
print('P4 contract summary',csvs(P/'INDEPENDENT_REFERENCE_SCORES.csv')[:3]);print('cases',[(x['title'],x['query_id'],x['view_id']) for x in json.loads((P/'CASEBOOK.json').read_text(encoding='utf-8'))]);print('paper roots',[p.name for p in (R/'论文材料').iterdir() if p.is_dir()]);print('P3R construct shape',str(json.loads((S/'construct/CONSTRUCT_RESULTS.json').read_text(encoding='utf-8'))[0])[:3000])
