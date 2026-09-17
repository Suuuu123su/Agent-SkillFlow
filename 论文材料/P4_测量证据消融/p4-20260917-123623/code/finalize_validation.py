from common import *
import shutil

guard();p=next((OUT/'zip_validation/reproductions').glob('*/PORTABLE_RECOMPUTE.json'));r=read(p);assert r['results']==832 and not r['errors'];dump('checks/ZIP_ROUNDTRIP_RECOMPUTE.json',r)
s=read(OUT/'P4_STATUS.json');s['targeted_engineering']['packaging_status']='CANDIDATE_ARCHIVE_ROUNDTRIP_PASS';s['targeted_engineering']['zip_roundtrip_results']=832;s['targeted_engineering']['zip_roundtrip_differences']=0;dump('P4_STATUS.json',s)
freeze=read(OUT/'audit/FULL_SWEEP_START.json');assert freeze['predictor_sha256']==sha(OUT/'code/predictor.py');assert freeze['views_sha256']==sha(OUT/'code/views.py');assert freeze['query_registry_sha256']==sha(OUT/'QUERY_REGISTRY.jsonl');assert freeze['base_sha256']==sha(OUT/'minimal_data/BASE_DOCUMENTS.jsonl')
dump('checks/FINAL_FREEZE_CHECK.json',{'predictor_unchanged':True,'view_algorithm_unchanged':True,'query_registry_unchanged':True,'base_facts_unchanged':True,'full_sweeps':1,'roundtrip_verified_queries_per_view':64,'roundtrip_full_sweep_repeated':False})
p=OUT/'P4_FINAL_REPORT.md';text=p.read_text(encoding='utf-8').replace('最终ZIP解包验证单独记录，不重复全量扫掠。','候选审查ZIP实际解包后再次复算64×13=832条，逐项差异0；最终包沿用同一输入、预测器和视图算法并逐成员校验。不重复全量扫掠。');p.write_text(text,encoding='utf-8')
print('ZIP roundtrip 832/832 exact; frozen query/base/analyzer unchanged')
