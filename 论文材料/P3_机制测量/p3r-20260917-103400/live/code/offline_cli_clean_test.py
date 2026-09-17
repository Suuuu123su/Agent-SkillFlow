"""Offline CLI wire inspection; local synthetic SSE only; never forwards network."""
import json,os,subprocess,threading,time,hashlib
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parent.parent
CLI=Path('C:/Users/Suziyu/AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe')
OFF=ROOT/'offline_cli';HOME=OFF/'clean_home';WORK=Path('E:/Skill ＆ Harness/tmp/p3r-20260917-103400/00000')
HOME.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
SCHEMA={'type':'object','properties':{'text':{'type':'string'},'tool_calls':{'type':'array','items':{'type':'object','properties':{'name':{'type':'string'},'arguments':{'type':'string'}},'required':['name','arguments'],'additionalProperties':False}}},'required':['text','tool_calls'],'additionalProperties':False}
(OFF/'schema.json').write_text(json.dumps(SCHEMA),encoding='utf-8')
for directory in [HOME,WORK,*WORK.parents]:
 assert not any((directory/n).exists() for n in ['AGENTS.md','AGENTS.override.md']),str(directory)
requests=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  self.send_response(404);self.end_headers()
 def do_POST(self):
  raw=self.rfile.read(int(self.headers.get('Content-Length','0')))
  # Do not save authorization or arbitrary headers even in a mock-only test.
  auth_present=bool(self.headers.get('Authorization'))
  try:body=json.loads(raw)
  except Exception:body={'decode_error':True,'encoding':self.headers.get('Content-Encoding'),'length':len(raw)}
  requests.append({'path':self.path,'body':body,'authorization_present':auth_present})
  (OFF/'mock_requests.json').write_text(json.dumps(requests,ensure_ascii=False,indent=2),encoding='utf-8')
  if len(requests)>2:
   self.send_response(429);self.end_headers();return
  final=json.dumps({'text':'LOCAL_FIXTURE_OK','tool_calls':[]})
  item={'id':'msg_local','type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':final,'annotations':[]}],'phase':'final_answer'}
  response={'id':'resp_local','object':'response','created_at':int(time.time()),'model':'gpt-5.6-luna','status':'completed','output':[item],'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2}}
  events=[{'type':'response.created','response':{**response,'status':'in_progress','output':[]}},{'type':'response.output_item.added','output_index':0,'item':{**item,'status':'in_progress','content':[]}},{'type':'response.content_part.added','item_id':'msg_local','output_index':0,'content_index':0,'part':{'type':'output_text','text':'','annotations':[]}},{'type':'response.output_text.delta','item_id':'msg_local','output_index':0,'content_index':0,'delta':final},{'type':'response.output_text.done','item_id':'msg_local','output_index':0,'content_index':0,'text':final},{'type':'response.output_item.done','output_index':0,'item':item},{'type':'response.completed','response':response}]
  payload=''.join('event: '+x['type']+'\ndata: '+json.dumps(x)+'\n\n' for x in events).encode()
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
def config(port):
 cfg={'model':'gpt-5.6-luna','model_provider':'p2_mock','model_reasoning_effort':'medium','model_catalog_json':str(OFF/'bundled_models.json'),'project_doc_max_bytes':0,'web_search':'disabled','skills.include_instructions':False,'tools.update_plan.enabled':False,'suppress_unstable_features_warning':True,'model_auto_compact_token_limit':1000000000,'model_providers.p2_mock.name':'OpenAI','model_providers.p2_mock.base_url':f'http://127.0.0.1:{port}/backend-api/codex','model_providers.p2_mock.wire_api':'responses','model_providers.p2_mock.requires_openai_auth':False,'model_providers.p2_mock.supports_websockets':False,'model_providers.p2_mock.request_max_retries':0,'model_providers.p2_mock.stream_max_retries':0,'otel.exporter':'none','otel.trace_exporter':'none','otel.metrics_exporter':'none','otel.log_user_prompt':False}
 for f in ['shell_tool','apply_patch_freeform','view_image','plugins','apps','browser_use','computer_use','workspace_dependencies','skill_search','skill_mcp_dependency_install','tool_suggest','multi_agent','sleep_tool','shell_snapshot','memories','responses_websockets','responses_websockets_v2','enable_request_compression']:
  cfg['features.'+f]=False
 cfg['features.skip_host_skill_discovery']=True
 return cfg
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
from cli_settings import arguments
args,cfg=arguments(WORK,OFF,server.server_port,'offline-fixture-token',offline=True)
(OFF/'schema.json').write_text(json.dumps(SCHEMA),encoding='utf-8')
env={k:v for k,v in os.environ.items() if not any(s in k.upper() for s in ['TOKEN','API_KEY','CODEX','OPENAI','PROXY'])}
env.update(CODEX_HOME=str(HOME),TEMP=str(ROOT/'tmp'),TMP=str(ROOT/'tmp'),TMPDIR=str(ROOT/'tmp'))
try:
 with (OFF/'mock_events.jsonl').open('w',encoding='utf-8') as out,(OFF/'mock_stderr.log').open('w',encoding='utf-8') as err:
  result=subprocess.run(args,input='Offline protocol fixture. Return the required JSON object with text LOCAL_FIXTURE_OK and empty tool_calls.',encoding='utf-8',cwd=WORK,env=env,stdout=out,stderr=err,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
 summary={'exit_code':result.returncode,'local_mock_requests':len(requests),'external_provider_requests':0,'synthetic_fixture_not_model_inference':True,'wire_models':[x['body'].get('model') for x in requests],'wire_paths':[x['path'] for x in requests],'wire_tools':[[t.get('name',t.get('type')) for t in x['body'].get('tools',[])] for x in requests],'authorization_sent_to_mock':any(x['authorization_present'] for x in requests),'reply_present':(OFF/'reply.json').exists(),'canary_absent':all('ISOLATION_CANARY' not in json.dumps(x['body']) for x in requests),'builtin_coding_persona_absent':all('You are Codex, an agent based' not in json.dumps(x['body']) for x in requests)}
 (OFF/'ISOLATION_POSITIVE_TEST.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary))
finally:server.shutdown();server.server_close()
