from common import *
p=OUT/'code/reproduce_offline.py';s=p.read_text(encoding='utf-8').replace("f'audit/{vid}.json'","f'audit/full-{vid}.json'");p.write_text(s,encoding='utf-8')
import shutil
original=OUT;dest=OUT/'checks/minimal_reference_roundtrip';dest.mkdir();(dest/'control').mkdir();(dest/'minimal_data').mkdir();shutil.copyfile(OUT/'minimal_data/REFERENCE_INPUTS_MIN.jsonl',dest/'control/REFERENCE_INPUTS.jsonl');shutil.copyfile(OUT/'minimal_data/PREDICTOR_QUERIES.jsonl',dest/'minimal_data/PREDICTOR_QUERIES.jsonl');shutil.copyfile(OUT/'QUERY_REGISTRY.jsonl',dest/'QUERY_REGISTRY.jsonl')
import common
common.OUT=dest
import independent_reference
independent_reference.main()
a={r['query_id']:(r['eligibility'],r['value'],r['truth_available']) for r in rows(original/'GOLD_PROVENANCE.jsonl')};b={r['query_id']:(r['eligibility'],r['value'],r['truth_available']) for r in rows(dest/'GOLD_PROVENANCE.jsonl')};assert a==b
(dest/'MINIMAL_REFERENCE_CHECK.json').write_text(canonical({'queries':len(a),'differences':0,'private_provider_transcripts_needed':False}),encoding='utf-8');print('Minimal evaluator inputs independently reproduce',len(a),'gold rows')
