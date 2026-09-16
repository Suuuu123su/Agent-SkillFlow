"""Shared isolated CLI config; local wire guard forwards only to the fixed official backend."""
import os,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
CLI=Path('<USER_HOME>/AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe')
SCHEMA={'type':'object','properties':{'text':{'type':'string'},'tool_calls':{'type':'array','items':{'type':'object','properties':{'name':{'type':'string'},'arguments':{'type':'string'}},'required':['name','arguments'],'additionalProperties':False}}},'required':['text','tool_calls'],'additionalProperties':False}
def settings(port,token,offline=False):
 cfg={'model':'gpt-5.6-luna','model_provider':'p2_guard','model_reasoning_effort':'medium','model_catalog_json':str(ROOT/'offline_cli/bundled_models.json'),'model_instructions_file':str(ROOT/'code/cli_base_instructions.txt'),'project_doc_max_bytes':0,'web_search':'disabled','skills.include_instructions':False,'tools.update_plan.enabled':False,'suppress_unstable_features_warning':True,'model_auto_compact_token_limit':1000000000,'model_providers.p2_guard.name':'OpenAI','model_providers.p2_guard.base_url':f'http://127.0.0.1:{port}/backend-api/codex','model_providers.p2_guard.wire_api':'responses','model_providers.p2_guard.requires_openai_auth':not offline,'model_providers.p2_guard.supports_websockets':False,'model_providers.p2_guard.request_max_retries':0,'model_providers.p2_guard.stream_max_retries':0,'model_providers.p2_guard.http_headers':{'x-p2-binding':token},'otel.exporter':'none','otel.trace_exporter':'none','otel.metrics_exporter':'none','otel.log_user_prompt':False}
 for f in ['shell_tool','apply_patch_freeform','view_image','plugins','apps','browser_use','computer_use','workspace_dependencies','skill_search','skill_mcp_dependency_install','tool_suggest','multi_agent','sleep_tool','shell_snapshot','memories','responses_websockets','responses_websockets_v2','enable_request_compression']:cfg['features.'+f]=False
 cfg['features.skip_host_skill_discovery']=True
 return cfg

def environment(home,temp):
 env={k:v for k,v in os.environ.items() if not any(s in k.upper() for s in ['TOKEN','API_KEY','CODEX','OPENAI','PROXY','AGENT','SESSION','THREAD'])}
 env.update(CODEX_HOME=str(home),TEMP=str(temp),TMP=str(temp),TMPDIR=str(temp),PYTHONIOENCODING='utf-8')
 return env

def arguments(work,case,port,token,offline=False):
 args=[str(CLI),'exec','--ignore-user-config','--ephemeral','--sandbox','read-only','--skip-git-repo-check','-C',str(work),'--json','--output-schema',str(case/'schema.json'),'-o',str(case/'reply.json')]
 cfg=settings(port,token,offline)
 for k,v in cfg.items():args.extend(['-c',k+'='+toml_value(v)])
 return args+['-'],cfg

def toml_value(v):
 if isinstance(v,dict):return '{'+', '.join(json.dumps(k)+' = '+toml_value(x) for k,x in v.items())+'}'
 return json.dumps(v)
