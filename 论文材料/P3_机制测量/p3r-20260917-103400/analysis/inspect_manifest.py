from common import *
x=read(OUT/'legacy/SOURCE_MANIFEST.json');print('source_shape',type(x).__name__,list(x)[:12] if isinstance(x,dict) else len(x)); print(str(x)[:1000])
x=read(OUT/'audit/PACK_VERIFICATION.json');print('pack',str(x)[:1000])
x=rows(OUT/'evidence/ALR_ORIGINAL_DATABASE_LOOKUP.jsonl')[0];print('alr_lookup_keys',list(x)); print({k:v for k,v in x.items() if k not in ['matching_events','request','decision','events']})
