import json,os,threading,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'monitor'))
from progress_writer import write_snapshot,utc_now
class State:
 def __init__(self):
  self.lock=threading.RLock();self.value=json.loads((ROOT/'ledger_state.json').read_text());self.done=threading.Event();self.thread=None
 def flush(self,event=None,unit=None):
  with self.lock:
   if event:
    now=utc_now();self.value['last_event_at']=now;self.value['events']=(self.value['events']+[{'at':now,'code':event,'unit_id':unit}])[-12:]
   temp=ROOT/'ledger_state.writing';temp.write_text(json.dumps(self.value,ensure_ascii=False,indent=2),encoding='utf-8')
   for attempt in range(50):
    try:
     os.replace(temp,ROOT/'ledger_state.json');break
    except PermissionError:
     if attempt==49:raise
     time.sleep(0.02)
   try:
    write_snapshot(ROOT/'public/progress.json',self.value)
    self.value.pop('monitor_projection_error',None)
   except OSError as error:
    # The durable ledger was saved above. A read-only dashboard failure must not abort a model request.
    self.value['monitor_projection_error']={'type':type(error).__name__,'at':utc_now()}
 def start(self,phase):
  with self.lock:
   if self.value['requests']['in_flight']:raise RuntimeError('unsettled_request_requires_audit_no_resend')
   self.value.update(state='RUNNING',phase=phase,heartbeat_at=utc_now())
   if self.value['started_at'] is None:self.value['started_at']=utc_now()
   self.flush('RUN_STARTED')
  def beat():
   while not self.done.wait(4):
    with self.lock:
     self.value['heartbeat_at']=utc_now()
     try:self.flush()
     except OSError as error:self.value['heartbeat_write_error']={'type':type(error).__name__,'at':utc_now()}
  self.thread=threading.Thread(target=beat,daemon=True);self.thread.start()
 def unit(self,uid):return next(x for x in self.value['units'] if x['unit_id']==uid)
 def begin(self,uid):
  with self.lock:
   u=self.unit(uid)
   if u['status']!='not_started':raise RuntimeError('unit_already_started_no_resample')
   u['status']='running';self.value['current']={'unit_id':uid,'eval_id':uid,'role':'idle','actor_turn':0};self.flush('UNIT_STARTED',uid)
 def end(self,runstate='READY'):
  self.done.set()
  if self.thread:self.thread.join(10)
  with self.lock:self.value.update(state=runstate,current={'role':'idle'},heartbeat_at=utc_now());self.flush('RUN_STOPPED' if runstate!='COMPLETED' else 'RUN_COMPLETED')
