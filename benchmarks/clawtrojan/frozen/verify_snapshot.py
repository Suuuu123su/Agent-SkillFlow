from pathlib import Path
import hashlib,json
r=Path(__file__).resolve().parent
m=json.loads((r/'MANIFEST.sha256.json').read_text())
for p,h in m.items():assert hashlib.sha256((r/p).read_bytes()).hexdigest()==h,p
s=json.loads((r/'results/SUMMARY.json').read_text(encoding='utf-8'))
x=next(x for x in s['rows'] if x['model']=='DeepSeek Pro' and x['arm']=='evidence')
assert (x['attack_C'],x['attack_P'],x['attack_S'],x['clean_S'],x['clean_P'])==(8,0,18,12,1)
assert len(json.loads((r/'results/DS_CASE_PROVENANCE.json').read_text()))==39
print('PASS: frozen file hashes and recorded result counts')
