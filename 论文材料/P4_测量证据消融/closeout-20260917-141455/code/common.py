from pathlib import Path
import json,csv,hashlib,sys,os
OUT=Path(__file__).resolve().parents[1];ROOT=next((p for p in OUT.parents if (p/'AGENTS.md').is_file() and (p/'src/skillflow').is_dir()),OUT);P4=OUT.parent/'p4-20260917-123623';P3R=ROOT/'论文材料/P3_机制测量/p3r-20260917-103400';PACK=OUT/'task_pack/SkillFlow_P4_Closeout_Codex'
def can(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def rows(p):return [json.loads(x) for x in Path(p).read_text(encoding='utf-8-sig').splitlines() if x.strip()]
def csvread(p):return list(csv.DictReader(Path(p).open(encoding='utf-8-sig')))
def dump(p,x):p=OUT/p;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def csvout(p,rr,fields=None):
 rr=list(rr);p=OUT/p;p.parent.mkdir(parents=True,exist_ok=True);fields=fields or list(dict.fromkeys(k for r in rr for k in r))
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fields);w.writeheader();w.writerows({k:can(v) if isinstance(v,(list,dict)) else v for k,v in r.items()} for r in rr)
def guard():
 def audit(ev,args):
  if ev.startswith(('socket.','subprocess.','os.system')):raise RuntimeError('CLOSEOUT_OFFLINE_NO_EXECUTOR')
  if ev=='open' and isinstance(args[0],(str,bytes)):
   p=Path(os.fsdecode(args[0])).resolve();mode=str(args[1] or '');flags=args[2] or 0
   if p.name in ['auth.json','.env'] or p.suffix=='.dpapi':raise RuntimeError('NO_KEY_ACCESS')
   if any(x in mode for x in 'wax+') or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT):assert p.is_relative_to(OUT),'new closeout outputs only'
 sys.addaudithook(audit)
def number(v):
 if v in ['',None]:return None
 if isinstance(v,(bool,int,float)):return v
 try:return int(v)
 except ValueError:
  try:return float(v)
  except ValueError:return v
STATES=['point','bounded','unknown','not_applicable','conflict','analysis_error']
FAMILIES={'V00':'Full','V01':'Receipt','V02':'Grant','V03':'Provenance','V04':'Counterfactual','V05':'TaskSuccess certificate','V06':'Session/Revocation','V07':'Scope/Lifetime','V08':'Original reason','V09':'Failure detail','V10':'Declared capability rules','V11':'Irrelevant metadata','V12':'Consistent opaque ID rename'}
# Fixed semantic relation convention, declared before observing counts. Other families have no standalone metric of their own.
SELF={'V03':{'Provenance'},'V04':{'CI'},'V05':{'TaskSuccess'},'V09':{'failure_taxonomy'},'V10':{'HIAA_pot_declared'}}
ORDER={'HIAA_run':0,'HIAA_Y':1,'HIAA_pot_observed':2,'HIAA_pot_declared':3,'ALR':4,'RIR':5,'UEA':6,'UEA_count':7,'Provenance':8,'CI':9,'TaskSuccess':10,'E_STS':11,'failure_taxonomy':12}
def display(metric,protocol=''):return 'STS_target_contract' if metric=='E_STS' else metric
