import json,csv,hashlib,os,sys
from pathlib import Path
OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[2];OLD=OUT.parent/'p3-20260916-232018';PACK=OUT/'task_pack/SkillFlow_P3R_CompleteMetrics60'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def rows(p):return [json.loads(l) for l in Path(p).read_text(encoding='utf-8-sig').splitlines() if l.strip()]
def dump(p,x):
 p=OUT/p;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def jl(p,x):
 p=OUT/p;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(json.dumps(v,ensure_ascii=False,default=str)+'\n' for v in x),encoding='utf-8')
def csvout(p,x):
 x=list(x);p=OUT/p;p.parent.mkdir(parents=True,exist_ok=True)
 if not x:return
 fields=list(dict.fromkeys(k for v in x for k in v))
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fields);w.writeheader();w.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict,tuple)) else v for k,v in a.items()} for a in x)
def table(phase,name):
 d=ROOT/f'datasets/t17-v2/stages/{phase}';m=read(d/'dataset-manifest.json')
 return [(v,f'{(d/p).relative_to(ROOT).as_posix()}#L{i}') for p in m['tables'][name+'.jsonl'] for i,v in enumerate(rows(d/p),1)]
def offline_guard():
 def audit(event,args):
  if event.startswith(('socket.connect','socket.bind','socket.getaddrinfo','subprocess.Popen','os.system')):raise RuntimeError('Offline network/process forbidden')
  if event=='open' and isinstance(args[0],(str,bytes)):
   p=Path(os.fsdecode(args[0])).resolve();mode=args[1] or '';flags=args[2] or 0
   if any(c in str(mode) for c in 'wax+') or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT):
    if not p.is_relative_to(OUT):raise RuntimeError('Write outside new output')
   elif p.name in ['auth.json','.env'] or p.suffix=='.dpapi':raise RuntimeError('Offline secret read forbidden')
 sys.addaudithook(audit)
