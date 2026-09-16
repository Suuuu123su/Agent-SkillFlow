"""One authorized Responses API; all-role accounting before final send; no retry."""
import json,time,copy,re,collections,os
from datetime import datetime,timezone
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError
from pathlib import Path
from transport_attack import StopCampaign,NoRedirect,canonical,sha,base_body,convert_messages,output_text,Actor,JudgeClient
ROOT=Path(__file__).resolve().parent.parent
MODEL='gpt-5.6-luna';ENDPOINT='https://api.openai.com/v1/responses';CAP=4096

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def rows(p):return [json.loads(s) for s in Path(p).read_text(encoding='utf-8').splitlines() if s.strip()] if Path(p).exists() else []
def write(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+'.writing');t.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(t,p)

class Provider:
 def __init__(self,key,state):
  self.key=key;self.state=state;self.raw=ROOT/'raw';self.raw.mkdir(exist_ok=True)
  self.counts=collections.Counter((x['unit'],x['role']) for x in rows(self.raw/'attempts.jsonl'))
 def append(self,name,value):
  text=canonical(value)
  if self.key:text=text.replace(self.key,'[REDACTED]')
  with (self.raw/name).open('a',encoding='utf-8') as f:f.write(text+'\n');f.flush();os.fsync(f.fileno())
 def admit(self,unit,role,body):
  if role not in {'actor','semantic','content','derived','judge'}:raise StopCampaign('ROLE_NOT_ALLOWED')
  if body.get('model')!=MODEL or body.get('store') is not False or body.get('max_output_tokens')!=8192:raise StopCampaign('WIRE_CONTRACT_MISMATCH')
  if body.get('reasoning')!={'effort':'medium'}:raise StopCampaign('REASONING_CONTRACT_MISMATCH')
  if any(k in body for k in ['base_url','endpoint','temperature','model_provider']):raise StopCampaign('WIRE_OVERRIDE_FORBIDDEN')
  if getattr(self,'requires_api_key',True) and (not self.key or self.key in canonical(body)):raise StopCampaign('CREDENTIAL_PAYLOAD_GUARD')
  value=self.state.value;q=value['requests']
  if q['in_flight']:raise StopCampaign('SERIAL_INFLIGHT_GUARD')
  if q['attempts']>=CAP:raise StopCampaign('GLOBAL_CAP')
  if self.state.unit(unit)['status'] not in {'running','awaiting_judge'}:raise StopCampaign('UNIT_NOT_ADMITTED')
  if (ROOT/'STOP_REQUEST.json').exists():raise StopCampaign('USER_STOP')
  if datetime.now(timezone.utc)>=datetime(2026,9,16,12,0,0,tzinfo=timezone.utc):raise StopCampaign('AUTHORIZED_DEADLINE_DISPATCH_STOP')
  if role=='judge':
   if sum(n for (u,r),n in self.counts.items() if r=='judge')>=47 or self.counts[unit,role]>=1:raise StopCampaign('JUDGE_CAP')
  else:
   actor=self.counts[unit,'actor'];aux=sum(self.counts[unit,r] for r in ('semantic','content','derived'))
   if actor+aux>=128:raise StopCampaign('UNIT_CAP')
   # Reserve the original 20 Actor requests independently of auxiliary use.
   if role!='actor' and aux>=108:raise StopCampaign('AUX_CAP_ACTOR_BUDGET_RESERVED')
   if role=='actor' and actor>=20:raise StopCampaign('ACTOR_CAP')
 def create(self,unit,role,body):
  with self.state.lock:
   self.admit(unit,role,body);q=self.state.value['requests'];aid=q['attempts']+1
   raw=canonical(body)
   req=Request(ENDPOINT,data=raw.encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+self.key},method='POST')
   self.append('attempts.jsonl',{'id':aid,'unit':unit,'role':role,'endpoint':ENDPOINT,'request':body,'request_sha256':sha(raw),'time':time.time()})
   self.counts[unit,role]+=1;q['attempts']+=1;q['in_flight']+=1;q['by_role'][role]=q['by_role'].get(role,0)+1
   self.state.value['current']={'unit_id':unit,'eval_id':unit,'role':role,'actor_turn':self.counts[unit,'actor']}
   self.state.unit(unit)['actor_turn']=self.counts[unit,'actor'];self.state.flush('REQUEST_SENT',unit)
  started=time.monotonic();record={'id':aid,'unit':unit,'role':role};unknown=False;failure=None;response=None
  try:
   with build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=240) as res:
    payload=res.read();record['http_status']=res.status
   try:response=json.loads(payload)
   except (ValueError,UnicodeError):failure='INVALID_RESPONSE_JSON'
   if response is not None:
    response=json.loads(canonical(response).replace(self.key,'[REDACTED]'));record['response']=response
  except HTTPError as e:
   record['http_status']=e.code
   try:
    safe=json.loads(e.read()).get('error',{});record.update({k:safe.get(k) for k in ('type','code','param')})
   except Exception:pass
   failure='PROVIDER_HTTP_'+str(e.code)
  except StopCampaign:failure='PROVIDER_REDIRECT_REFUSED'
  except Exception as e:record.update(error_type=type(e).__name__,unknown_delivery=True);unknown=True;failure='RESPONSE_UNKNOWN_NO_RETRY'
  finally:
   record['elapsed_s']=time.monotonic()-started;self.append('results.jsonl',record)
   with self.state.lock:
    q=self.state.value['requests'];q['in_flight']-=1;q['response_unknown' if unknown else 'settled']+=1
    self.state.flush('REQUEST_UNKNOWN' if unknown else 'REQUEST_SETTLED',unit)
  if failure:raise StopCampaign(failure)
  if not re.fullmatch(re.escape(MODEL)+r'(?:-\d{4}-\d{2}-\d{2})?',response.get('model','')):raise StopCampaign('RESPONSE_MODEL_MISMATCH')
  if response.get('error'):raise StopCampaign('PROVIDER_RESPONSE_ERROR')
  if response.get('status') not in {'completed','incomplete'}:raise StopCampaign('UNEXPECTED_RESPONSE_STATUS')
  if response.get('status')=='incomplete' and (response.get('incomplete_details') or {}).get('reason')!='max_output_tokens':raise StopCampaign('PROVIDER_RESTRICTION')
  for item in response.get('output',[]):
   if item.get('type') not in {'reasoning','message','function_call'}:raise StopCampaign('UNEXPECTED_OUTPUT_TYPE')
   if any(c.get('type')=='refusal' for c in item.get('content',[]) or []):raise StopCampaign('PROVIDER_REFUSAL')
  return response
 def clear(self):self.key=''

class DefenseProvider:
 def __init__(self,provider):self.provider=provider
 def create(self,unit,role,body,boundary=None):
  if role!='defense' or body.get('max_tokens')!=8192:raise StopCampaign('DEFENSE_SOURCE_CONTRACT')
  mapping={'dynamic_route':'semantic','content_check':'content','derived_check':'derived'}
  phase=(boundary or '').rsplit(':',1)[-1]
  if phase not in mapping:raise StopCampaign('UNMAPPED_DEFENSE_ROLE')
  wire=base_body(convert_messages(body['messages']))
  wire['input'].insert(0,{'role':'system','content':'Return the requested output as a JSON object.'});wire['text']={'format':{'type':'json_object'}}
  if wire['model']!=MODEL:raise StopCampaign('DEFENSE_FINAL_MODEL_NOT_LUNA')
  self.provider.append('defense_projection.jsonl',{'unit':unit,'boundary':boundary,'source_request':body,'wire_sha256':sha(canonical(wire)),'projection_model':MODEL,'role':mapping[phase]})
  response=self.provider.create(unit,mapping[phase],wire)
  return {'model':response['model'],'choices':[{'finish_reason':'stop' if response['status']=='completed' else 'length','message':{'role':'assistant','content':output_text(response)}}],'usage':response.get('usage',{})}
