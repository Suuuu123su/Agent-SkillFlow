"""Serial outer controller; each child batch admits at most two fresh slots.
Only unknown transport outcomes may be followed by DIFFERENT untouched units.
Any explicit provider rejection or isolation/cap failure stops all new dispatch.
"""
import subprocess,sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'live'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
log=ROOT/'batch_control.jsonl'
for batch in range(1,40):
 before=read(ROOT/'ledger.json');pending=[u for u,v in before['units'].items() if not u.startswith('TECH') and v['status']=='not_started']
 if not pending:print('FORMAL_SLOTS_SETTLED',flush=True);break
 ids=pending[:2];started=time.time();result=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'code/run_batch.py'),'formal'],capture_output=True,text=True,encoding='utf-8')
 record={'batch':batch,'intended_fresh_slots':ids,'max_units':2,'started':started,'ended':time.time(),'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
 with log.open('a',encoding='utf-8') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
 after=read(ROOT/'ledger.json');newstops=[u for u,v in after['units'].items() if v['status']=='transport_stopped' and before['units'][u]['status']=='not_started']
 stopreason=None
 for u in newstops:
  reason=after['units'][u]['details']['reason']
  if reason!='RESPONSE_UNKNOWN_NO_RETRY':stopreason=reason
 if result.returncode:stopreason='CHILD_ERROR'
 if before['requests']['attempts']==after['requests']['attempts'] and all(after['units'][u]['status']=='not_started' for u in ids):stopreason='NO_PROGRESS'
 print(json.dumps({'batch':batch,'slots':ids,'requests':after['requests'],'stop':stopreason}),flush=True)
 if stopreason:
  (ROOT/'CAMPAIGN_STOP.json').write_text(json.dumps({'reason':stopreason,'batch':batch,'newstops':newstops}),encoding='utf-8');break
