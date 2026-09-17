from common import *
for f in ['POT_SETS_AND_WITNESSES.json','construct/CONSTRUCT_RESULTS.json','live/FORMAL_CODE_FREEZE.json','audit/CI_CONTENT_SCHEMA_SENSITIVITY.json']:
 x=read(OUT/f)
 if f.startswith('POT'):print(f,{k:{j:v for j,v in x[k].items() if j!='model'} for k in x})
 elif f.startswith('construct'):print(f,x)
 else: print(f,x)
x=rows(OUT/'live/units/RIR-I1-target-R1-P/model_turns.jsonl')[0];print('model_turns keys',x.keys());print({k:(list(v) if isinstance(v,dict) else type(v).__name__) for k,v in x.items()})
