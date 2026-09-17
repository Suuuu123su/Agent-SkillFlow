"""P3R transport base: only Actor role, 60 immutable slots, no SDK/API route."""
import json,time,collections,os,hashlib,threading,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;OUT=ROOT.parent;MODEL='gpt-5.6-luna'
class StopCampaign(RuntimeError):pass
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(x):return hashlib.sha256(x if isinstance(x,bytes) else x.encode()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def rows(p):return [json.loads(s) for s in Path(p).read_text(encoding='utf-8-sig').splitlines() if s.strip()] if Path(p).exists() else []
def write(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
class State:
 def __init__(self):
  self.lock=threading.RLock();self.slots={r['slot_id']:r for r in csv.DictReader((OUT/'task_pack/SkillFlow_P3R_CompleteMetrics60/capacity_slots.csv').open(encoding='utf-8-sig'))}
  self.value=read(ROOT/'ledger.json') if (ROOT/'ledger.json').exists() else {'requests':{'attempts':0,'settled':0,'response_unknown':0,'in_flight':0,'by_role':{}},'units':{k:{'status':'not_started'} for k in self.slots},'created':time.time()}
 def unit(self,u):return self.value['units'][u]
 def flush(self,event,u):self.value['last_event']={'event':event,'unit':u,'time':time.time()};write(ROOT/'ledger.json',self.value)
class Provider:
 def __init__(self,key,state):
  self.state=state;self.raw=ROOT/'raw';self.raw.mkdir(exist_ok=True);self.counts=collections.Counter((x['unit'],x['role']) for x in rows(self.raw/'attempts.jsonl'))
 def append(self,name,v):
  with (self.raw/name).open('a',encoding='utf-8') as f:f.write(canonical(v)+'\n');f.flush();os.fsync(f.fileno())
 def admit(self,unit,role,body):
  if role!='actor':raise StopCampaign('ONLY_ACTOR_ALLOWED')
  if body.get('model')!=MODEL or body.get('store') is not False or body.get('max_output_tokens')!=8192 or body.get('reasoning')!={'effort':'medium'}:raise StopCampaign('MODEL_CONFIG_MISMATCH')
  if any(k in body for k in ['base_url','endpoint','temperature','model_provider']):raise StopCampaign('WIRE_OVERRIDE_FORBIDDEN')
  q=self.state.value['requests'];slot=self.state.slots.get(unit)
  if slot is None:raise StopCampaign('UNDECLARED_SLOT')
  if self.state.unit(unit)['status']!='running':raise StopCampaign('UNIT_NOT_ADMITTED')
  if q['in_flight']:raise StopCampaign('SERIAL_INFLIGHT_GUARD')
  if q['attempts']>=min(1152,1104):raise StopCampaign('HARD_CAP')
  if self.counts[unit,'actor']>=int(slot['max_requests']):raise StopCampaign('UNIT_CAP')
  if time.time()>read(OUT/'SUPPLEMENT_ACTIVATION.json')['stop_new_dispatch_unix']:raise StopCampaign('24H_DISPATCH_STOP')
  if (ROOT/'STOP_REQUEST.json').exists():raise StopCampaign('USER_STOP')
  if any(x in canonical(body) for x in ['api_key','Authorization: Bearer','BEGIN PRIVATE KEY']):raise StopCampaign('SECRET_PATTERN_IN_PAYLOAD')
