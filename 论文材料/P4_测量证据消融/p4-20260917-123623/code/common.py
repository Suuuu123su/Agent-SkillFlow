import json,csv,hashlib,os,sys
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]; ROOT=OUT.parents[2]; P3R=ROOT/'论文材料/P3_机制测量/p3r-20260917-103400'; P3=P3R.parent/'p3-20260916-232018'; PACK=OUT/'task_pack/SkillFlow_P4_MeasurementEvidenceAblation'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def rows(p):return [json.loads(x) for x in Path(p).read_text(encoding='utf-8-sig').splitlines() if x.strip()]
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def dump(p,x):
 p=OUT/p;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def jl(p,x):
 p=OUT/p;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(canonical(v)+'\n' for v in x),encoding='utf-8')
def csvout(p,x,fields=None):
 x=list(x);p=OUT/p;p.parent.mkdir(parents=True,exist_ok=True);fields=fields or list(dict.fromkeys(k for r in x for k in r))
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fields);w.writeheader();w.writerows({k:canonical(v) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in x)
def guard():
 def audit(ev,args):
  if ev.startswith(('socket.connect','socket.bind','socket.getaddrinfo','subprocess.Popen','os.system')):raise RuntimeError('P4_OFFLINE_NO_PROCESS_NETWORK')
  if ev=='open' and isinstance(args[0],(str,bytes)):
   p=Path(os.fsdecode(args[0])).resolve();mode=args[1] or '';flags=args[2] or 0
   if p.name in ['auth.json','.env'] or p.suffix=='.dpapi' or 'private_codex_home' in p.parts:raise RuntimeError('P4_NO_CREDENTIAL_ACCESS')
   if any(c in str(mode) for c in 'wax+') or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT):
    if not p.is_relative_to(OUT):raise RuntimeError('P4_WRITE_OUTSIDE_NEW_OUTPUT')
 sys.addaudithook(audit)
def table(phase,name):
 d=ROOT/f'datasets/t17-v2/stages/{phase}';m=read(d/'dataset-manifest.json')
 return [(x,(d/p).relative_to(ROOT).as_posix()+f'#L{i}') for p in m['tables'][name+'.jsonl'] for i,x in enumerate(rows(d/p),1)]
