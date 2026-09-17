"""Measured local Codex CLI transport. No API SDK, key loading or provider fallback.
A loopback send guard admits every actual CLI POST, filtering host capability declarations before forwarding to
one fixed official endpoint. Authorization is forwarded in memory, never recorded.
"""
import json,os,time,threading,subprocess,secrets,http.client,socket,copy,collections
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import p2_transport as base
from cli_settings import ROOT,CLI,SCHEMA,arguments,environment
UPSTREAM_HOST='chatgpt.com'
UPSTREAM_PATH='/backend-api/codex/responses'
UPSTREAM_URL='https://'+UPSTREAM_HOST+UPSTREAM_PATH

class Provider(base.Provider):
 requires_api_key=False
 def __init__(self,unused,state):
  super().__init__(None,state)
  self.home=ROOT/'private_codex_home'
  if not (self.home/'auth.json').is_file():raise base.StopCampaign('CLI_LOGIN_CACHE_MISSING')
  if any((self.home/n).exists() for n in ['AGENTS.md','AGENTS.override.md','config.toml']):raise base.StopCampaign('ISOLATION_HOME_CONTAMINATED')
  if not (ROOT/'CLI_OFFLINE_ADMISSION.json').is_file():raise base.StopCampaign('CLI_OFFLINE_ADMISSION_MISSING')
  if not base.read(ROOT/'CLI_OFFLINE_ADMISSION.json')['passed']:raise base.StopCampaign('CLI_OFFLINE_ADMISSION_FAILED')
  self.invocations=len(base.rows(self.raw/'cli_invocations.jsonl'))
 def create(self,unit,role,body):
  with self.state.lock:self.admit(unit,role,body)
  self.invocations+=1;call=self.invocations;case=self.raw/f'cli_{call:05d}';case.mkdir(exist_ok=False)
  # Only numeric opaque paths go into CLI environment context; no arm/task identifiers.
  work=Path('E:/Skill ＆ Harness/tmp/p3r-20260917-103400')/f'{os.getpid()}-{call:05d}';work.mkdir(parents=True,exist_ok=False)
  temp=case/'temp';temp.mkdir();base.write(case/'schema.json',SCHEMA)
  visible=[x for x in body['input'] if x.get('type')!='reasoning']
  prompt=('Produce exactly the next assistant turn for the conversation below. Return text and proposed tool_calls in the required JSON schema. Tool arguments must be a JSON string. Use only tools listed in the supplied tool definitions; an external isolated harness will execute them. Do not execute host tools, read local files, or use external services. If no tools are listed, tool_calls must be empty. If the conversation requests JSON, place that JSON in the text string.\n'+base.canonical({'conversation':visible,'tools':body.get('tools',[])}))
  guard=SendGuard(self,unit,role,body,case,prompt)
  server=ThreadingHTTPServer(('127.0.0.1',0),guard.handler());server.daemon_threads=True
  worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
  args,cfg=arguments(work,case,server.server_port,guard.token)
  public_cfg={k:v for k,v in cfg.items() if not k.endswith('http_headers')}
  self.append('cli_invocations.jsonl',{'call':call,'unit':unit,'role':role,'time':time.time(),'cli_sha256':base.sha(CLI.read_bytes()),'config':public_cfg,'work':str(work),'requested_max_output_tokens':8192,'cli_output_cap_supported':False,'provider_attempts_are_guard_events_not_invocation_count':True})
  returncode=None
  try:
   with (case/'events.jsonl').open('w',encoding='utf-8') as out,(case/'stderr.log').open('w',encoding='utf-8') as err:
    proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=out,stderr=err,cwd=work,env=environment(self.home,temp),creationflags=subprocess.CREATE_NO_WINDOW)
    base.write(case/'PROCESS.json',{'pid':proc.pid,'started_at':time.time(),'unit':unit,'role':role})
    try:proc.communicate(prompt.encode('utf-8'),timeout=600)
    except subprocess.TimeoutExpired:
     proc.kill();proc.communicate();guard.failure=guard.failure or 'CLI_TIMEOUT_NO_RESEND'
    returncode=proc.returncode
   guard.finished.wait(10)
  finally:
   server.shutdown();server.server_close();worker.join(3)
   base.write(case/'GUARD_SUMMARY.json',{'actual_forwarded_attempts':guard.forwarded,'rejected_local_requests':guard.rejected,'response_complete':guard.completed,'failure':guard.failure,'cli_returncode':returncode,'upstream':UPSTREAM_URL,'authorization_recorded':False})
  if guard.failure:raise base.StopCampaign(guard.failure)
  if guard.forwarded!=1 or not guard.completed:raise base.StopCampaign('CLI_WIRE_ACCOUNTING_UNRESOLVED')
  events=base.rows(case/'events.jsonl')
  if returncode or any(e.get('type') in ('error','turn.failed') for e in events):raise base.StopCampaign('CLI_EXECUTION_FAILED')
  if any(e.get('type')=='item.completed' and e.get('item',{}).get('type') not in ('agent_message','reasoning') for e in events):raise base.StopCampaign('UNEXPECTED_CLI_HOST_TOOL')
  try:value=base.read(case/'reply.json')
  except Exception:raise base.StopCampaign('CLI_REPLY_UNAVAILABLE')
  names={t['name'] for t in body.get('tools',[])};output=[]
  if not isinstance(value.get('text'),str) or not isinstance(value.get('tool_calls'),list):raise base.StopCampaign('CLI_REPLY_SCHEMA')
  if value['text']:output.append({'type':'message','role':'assistant','content':[{'type':'output_text','text':value['text']}]})
  for i,c in enumerate(value['tool_calls']):
   if c.get('name') not in names:raise base.StopCampaign('UNLISTED_PROPOSED_TOOL')
   try:json.loads(c['arguments'])
   except Exception:raise base.StopCampaign('INVALID_PROPOSED_TOOL_JSON')
   output.append({'type':'function_call','call_id':f'cli_{call}_{i}','name':c['name'],'arguments':c['arguments']})
  usage=guard.final_response.get('usage',{})
  response={'model':base.MODEL,'status':'completed','output':output,'usage':usage,'model_identity_source':'actual_final_wire_request_checked; returned metadata preserved separately','actual_response_model':guard.final_response.get('model')}
  self.append('cli_projected_results.jsonl',{'call':call,'unit':unit,'role':role,'response':response})
  return response

def isolate_wire(wire):
 """Remove CLI host capability declarations, retaining all text/permission messages."""
 value=copy.deepcopy(wire);removed=[];kept=[]
 for i,item in enumerate(value.get('input',[])):
  if item.get('tools'):
   if item.get('role')!='developer':raise ValueError('UNEXPECTED_TOOL_DECLARATION_LOCATION')
   removed.append({'input_index':i,'tools':item['tools']});item.pop('tools')
   if not item.get('content'):continue
  kept.append(item)
 value['input']=kept
 if value.get('tools'):raise ValueError('UNEXPECTED_TOP_LEVEL_HOST_TOOLS')
 value['tool_choice']='none'
 return value,removed

class SendGuard:
 def __init__(self,provider,unit,role,virtual_body,case,prompt):
  self.p=provider;self.unit=unit;self.role=role;self.virtual=virtual_body;self.case=case;self.prompt=prompt
  self.token=secrets.token_urlsafe(32);self.lock=threading.Lock();self.forwarded=0;self.rejected=0;self.completed=False;self.failure=None;self.final_response={};self.finished=threading.Event()
 def validate(self,path,headers,raw):
  if path!=UPSTREAM_PATH:raise ValueError('CLI_ROUTE_NOT_ALLOWED')
  if headers.get('x-p2-binding')!=self.token:raise ValueError('CLI_BINDING_TOKEN_MISMATCH')
  if headers.get('Content-Encoding') not in (None,'identity'):raise ValueError('CLI_WIRE_ENCODING_UNVERIFIED')
  wire=json.loads(raw)
  if wire.get('model')!=base.MODEL:raise ValueError('FINAL_WIRE_MODEL_NOT_LUNA')
  if wire.get('tools'):raise ValueError('HOST_TOOLS_EXPOSED')
  if wire.get('store') is not False or wire.get('stream') is not True:raise ValueError('CLI_STREAM_CONTRACT')
  if wire.get('reasoning',{}).get('effort')!='medium':raise ValueError('CLI_REASONING_CONTRACT')
  items=wire.get('input',[])
  def texts(item):
   c=item.get('content','');return c if isinstance(c,str) else ''.join(x.get('text','') for x in c)
  if not items or items[-1].get('role')!='user' or texts(items[-1])!=self.prompt:raise ValueError('WRAPPER_PROMPT_MISMATCH')
  earlier='\n'.join(texts(x) for x in items[:-1])
  if any(x in earlier for x in ['<skills_instructions>','<user_instructions>','# AGENTS.md instructions','MEMORY_SUMMARY','ISOLATION_CANARY']):raise ValueError('HOST_CONTEXT_LEAK')
  if not headers.get('Authorization','').startswith('Bearer '):raise ValueError('CLI_AUTH_HEADER_MISSING')
  return wire
 def handler(self):
  guard=self
  class Handler(BaseHTTPRequestHandler):
   protocol_version='HTTP/1.1'
   def log_message(self,*a):pass
   def reject(self,code):
    guard.rejected+=1;guard.failure=guard.failure or code
    payload=json.dumps({'error':{'type':'local_execution_guard','code':code,'message':'Local execution guard stopped this request; no retry is permitted.'}}).encode()
    self.send_response(409);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.send_header('Connection','close');self.end_headers();self.wfile.write(payload)
   def do_GET(self):self.reject('CLI_UNEXPECTED_GET')
   def do_POST(self):
    with guard.lock:
     if guard.forwarded:self.reject('SECOND_INTERNAL_REQUEST_BLOCKED_NO_RETRY');return
     if self.headers.get('Transfer-Encoding'):self.reject('CLI_UNEXPECTED_CHUNKED_REQUEST');return
     length=int(self.headers.get('Content-Length','0'))
     if length<=0 or length>32*1024*1024:self.reject('CLI_REQUEST_SIZE');return
     raw=self.rfile.read(length)
     try:
      original_sha=base.sha(raw);wire=guard.validate(self.path,self.headers,raw)
      wire,removed=isolate_wire(wire)
      base.write(guard.case/'HOST_CAPABILITIES_REMOVED.json',{'original_request_sha256':original_sha,'removed':removed,'text_messages_preserved':True,'revision':'r2_host_tools_removed'})
      raw=json.dumps(wire,ensure_ascii=False,separators=(',',':')).encode('utf-8')
     except Exception as e:self.reject(str(e) if isinstance(e,ValueError) else 'CLI_REQUEST_INVALID');return
     p=guard.p;state=p.state
     with state.lock:
      try:p.admit(guard.unit,guard.role,guard.virtual)
      except base.StopCampaign as e:self.reject(str(e));return
      q=state.value['requests'];aid=q['attempts']+1
      p.append('attempts.jsonl',{'id':aid,'unit':guard.unit,'role':guard.role,'time':time.time(),'endpoint':UPSTREAM_URL,'request':wire,'request_sha256':base.sha(raw),'transport':'isolated_codex_cli_guarded','authorization_recorded':False,'protocol_revision':'r2_host_tools_removed','transport_patch':'r2.1_terminal_accounting','cli_original_request_sha256':original_sha})
      p.counts[guard.unit,guard.role]+=1;q['attempts']+=1;q['in_flight']+=1;q['by_role'][guard.role]=q['by_role'].get(guard.role,0)+1
      state.value['current']={'unit_id':guard.unit,'eval_id':guard.unit,'role':guard.role,'actor_turn':p.counts[guard.unit,'actor']};state.unit(guard.unit)['actor_turn']=p.counts[guard.unit,'actor'];state.flush('REQUEST_SENT',guard.unit)
      guard.forwarded+=1
     # The only external destination is this fixed HTTPS host/path. Never follow redirects.
     connection=http.client.HTTPSConnection(UPSTREAM_HOST,timeout=240)
     headers={k:v for k,v in self.headers.items() if k.lower() not in {'host','content-length','connection','proxy-connection','transfer-encoding','x-p2-binding','accept-encoding'}}
     headers['Accept-Encoding']='identity';headers['Content-Length']=str(len(raw))
     started=time.monotonic();status=None;unknown=True;client_gone=False;buffered=[];transport_phase="before_send";transport_error_type=None
     try:
      transport_phase='sending_request'
      connection.request('POST',UPSTREAM_PATH,body=raw,headers=headers)
      transport_phase='waiting_response_headers'
      res=connection.getresponse();status=res.status;transport_phase='reading_response_body'
      self.send_response(status)
      for k,v in res.getheaders():
       if k.lower() in {'content-type','x-request-id'}:self.send_header(k,v)
      self.send_header('Connection','close');self.end_headers()
      with (guard.case/'provider_response.sse').open('wb') as out:
       while True:
        line=res.readline()
        if not line:break
        out.write(line)
        buffered.append(line)
        if line.startswith(b'data: '):
         try:event=json.loads(line[6:])
         except (ValueError,UnicodeError):continue
         if event.get('type') in ('response.completed','response.incomplete','response.failed'):
          guard.final_response=event.get('response',{});guard.completed=event.get('type')=='response.completed';unknown=False
      host_calls=any(x.get('type') not in ('message','reasoning') for x in guard.final_response.get('output',[]))
      if host_calls:
       guard.failure='HOST_TOOL_RESPONSE_BLOCKED_BEFORE_CLI';unknown=False
      elif guard.completed:
       for line in buffered:
        try:self.wfile.write(line);self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError,OSError):break
      if status!=200:
       unknown=False;guard.failure='PROVIDER_HTTP_'+str(status)
      elif not guard.completed:guard.failure='RESPONSE_UNKNOWN_NO_RETRY' if unknown else 'CLI_PROVIDER_RESPONSE_UNRESOLVED'
      elif guard.final_response.get('model') and not guard.final_response['model'].startswith(base.MODEL):guard.failure='RETURNED_MODEL_MISMATCH'
     except Exception as e:
      transport_error_type=type(e).__name__;guard.failure='RESPONSE_UNKNOWN_NO_RETRY'
     finally:
      headers.clear();connection.close()
      p.append('results.jsonl',{'id':aid,'unit':guard.unit,'role':guard.role,'http_status':status,'elapsed_s':time.monotonic()-started,'unknown_delivery':unknown,'response':guard.final_response,'failure':guard.failure,'transport_phase':transport_phase,'transport_error_type':transport_error_type})
      with state.lock:
       q=state.value['requests'];q['in_flight']-=1;q['response_unknown' if unknown else 'settled']+=1;state.flush('REQUEST_UNKNOWN' if unknown else 'REQUEST_SETTLED',guard.unit)
      guard.finished.set();self.close_connection=True
  return Handler
