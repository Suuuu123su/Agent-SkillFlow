"""Single-real-environment route: 24 development + 32 heldout + 16 interventions.

Official deterministic provider replaces only model decisions. Native OpenClaw
agent routing, policy filtering, path checking and write tools remain in use.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

from experiments.evidence_contract_validation.common import (
    ROOT, append_json, frozen_json, load_frozen, now, read_json, sha, write_json)
from .pilot_spec import FAMILIES,scenario
from .pilot_oracle import evaluate


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));return s.getsockname()[1]


def environment(temp):
    e={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','PATH','PATHEXT','COMSPEC','PROCESSOR_ARCHITECTURE')}
    e.update(TEMP=str(temp),TMP=str(temp),PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    return e


def sources():
    files=list(Path(__file__).parent.glob('pilot_*.py'))
    files+=list((ROOT/'src/skillflow/graph').glob('*.py'))
    return {p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in files}


def verify_sources(plan):
    for rel,digest in plan['source_hashes'].items():
        if sha((ROOT/rel).read_bytes())!=digest:raise ValueError('Frozen pilot code changed: '+rel)


def predict_all(specs,out):
    private=out/'predictor_private';private.mkdir(exist_ok=True)
    command=[sys.executable,'-B','-I',str(Path(__file__).with_name('pilot_predict.py'))]
    process=subprocess.run(command,input=''.join(json.dumps(s['input'])+'\n' for s in specs),
                           capture_output=True,text=True,encoding='utf-8',cwd=private,env=environment(private),timeout=120)
    if process.returncode:raise RuntimeError(process.stderr)
    answers=[json.loads(s) for s in process.stdout.splitlines()]
    if len(answers)!=len(specs):raise ValueError('Incomplete predictions')
    return [{'unit_id':s['unit_id'],'input_sha256':sha(json.dumps(s['input'],sort_keys=True).encode()),
             'at':now(),'prediction':a} for s,a in zip(specs,answers)]


def snapshot(folder):
    paths=[folder/'protected.txt',*sorted((folder/'workspace').rglob('*'))]
    return {p.relative_to(folder).as_posix():{'sha256':sha(p.read_bytes()),'content_utf8':p.read_text('utf-8')}
            for p in paths if p.is_file()}


def response_script(spec,folder):
    responses=[]
    for index,action in enumerate(spec['input']['actions']):
        target=(folder/action['resource']).resolve()
        if folder not in target.parents:raise ValueError('Action escapes registered temporary unit')
        args={'path':str(target),'content':action['content']}
        ident=f"{spec['unit_id']}-{index}"
        item={'type':'function_call','id':'fc_'+ident,'call_id':'call_'+ident,'name':action['tool'],'arguments':json.dumps(args)}
        responses.append({'events':[
            {'type':'response.output_item.added','item':item|{'arguments':''}},
            {'type':'response.function_call_arguments.delta','delta':json.dumps(args)},
            {'type':'response.output_item.done','item':item},
            {'type':'response.completed','response':{'id':'resp_'+ident,'status':'completed','output':[item],
                'usage':{'input_tokens':0,'output_tokens':0,'total_tokens':0}}}]})
    responses.append({'text':'REGISTERED_SEQUENCE_FINISHED'})
    return {'scriptVersion':spec['unit_id'],'responses':responses,'default':{'text':'REGISTERED_SEQUENCE_FINISHED'}}


def execute_group(out,package,specs,phase,group,plan_path):
    ledger=out.parent/'EXECUTION_LEDGER.jsonl'
    groupdir=out/'runtime'/phase/group
    if groupdir.exists():groupdir=out/'runtime'/phase/(group+'-retry-02')
    groupdir.mkdir(parents=True,exist_ok=False)
    for d in ('state','temp','home','empty'):(groupdir/d).mkdir()
    port,mock_port=free_port(),free_port()
    while mock_port==port:mock_port=free_port()
    units=[]
    for spec in specs:
        rows=[json.loads(s) for s in ledger.read_text('utf-8').splitlines() if s]
        if len(rows)>=96:raise ValueError('Single-environment cap exhausted')
        prior=[r for r in rows if r.get('unit_id')==spec['unit_id']]
        attempt=len(prior)+1
        if prior and (attempt!=2 or spec['unit_id'] not in load_frozen(plan_path).get('retryable_infrastructure_units',[])):
            raise ValueError('No business retry; infrastructure retry at most once')
        if len(spec['input']['actions'])>16:raise ValueError('Action cap')
        append_json(ledger,{'ordinal':len(rows)+1,'at':now(),'phase':phase,'unit_id':spec['unit_id'],
                           'family_id':spec['family_id'],'combination':spec['combination'],'condition':spec['condition'],
                           'arm':spec['arm'],'attempt':attempt,'model_calls':0,'actions_cap':16,
                           'plan_sha256':sha(plan_path.read_bytes()),'state':'COUNTED_BEFORE_INITIALIZATION'})
        folder=out/'raw'/spec['unit_id']
        if attempt==2:folder=folder/'attempt-02'
        folder.mkdir(parents=True,exist_ok=False)
        (folder/'workspace').mkdir();(folder/'protected.txt').write_bytes(b'PROTECTED_ORIGINAL\n')
        for rel,content in spec['initial'].items():
            p=folder/'workspace'/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content.encode('utf-8'))
        write_json(folder/'SPEC.json',spec,exclusive=True)
        write_json(folder/'BEFORE.json',snapshot(folder),exclusive=True)
        units.append((spec,folder))
    native=specs[0]['input']['native']; model_ref='openai/local-script'
    defaults={'workspace':str(groupdir/'empty'),'model':{'primary':model_ref},
              'models':{model_ref:{'params':{'transport':'sse','openaiWsWarmup':False}}}}
    cfg={'agents':{'ownership':'explicit','defaults':defaults,'list':[{'id':s['unit_id'],'workspace':str(f/'workspace'),'agentDir':str(groupdir/'state'/s['unit_id'])} for s,f in units]},
         'gateway':{'mode':'local','bind':'loopback','port':port,'auth':{'mode':'token','token':'local-research-placeholder'},
                    'controlUi':{'enabled':False},'http':{'endpoints':{'responses':{'enabled':True}}}},
         'tools':{'allow':native['allowed_tools'],'fs':{'workspaceOnly':native['workspace_only']}},
         'skills':{'allowBundled':[]},'plugins':{'enabled':False},
         'logging':{'file':str(groupdir/'gateway.log'),'level':'debug' if specs[0]['arm']=='unrelated' else 'info'},
         'models':{'mode':'merge','providers':{'openai':{'baseUrl':f'http://127.0.0.1:{mock_port}/v1',
                   'apiKey':'local-script-placeholder','api':'openai-responses','request':{'allowPrivateNetwork':True},
                   'models':[{'id':'local-script','name':'local-script','api':'openai-responses','reasoning':False,'input':['text'],
                              'contextWindow':128000,'maxTokens':1024,'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0}}]}}}}
    write_json(groupdir/'config.json',cfg,exclusive=True)
    write_json(groupdir/'response-control.json',{'text':'BOOT'})
    env=environment(groupdir/'temp')
    env.update(OPENCLAW_HOME=str(groupdir/'home'),OPENCLAW_CONFIG_PATH=str(groupdir/'config.json'),OPENCLAW_STATE_DIR=str(groupdir/'state'),
               OPENCLAW_NO_RESPAWN='1',OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_SKIP_STARTUP_MODEL_PREWARM='1',
               MOCK_PORT=str(mock_port),MOCK_RESPONSE_CONTROL=str(groupdir/'response-control.json'),MOCK_REQUEST_LOG=str(groupdir/'scripted_requests.jsonl'))
    gateway=provider=None;begin=time.monotonic()
    try:
        with (groupdir/'stdout.txt').open('x',encoding='utf-8') as stdout,(groupdir/'stderr.txt').open('x',encoding='utf-8') as stderr:
            provider=subprocess.Popen(['E:/Node/node.exe',str(out/'source/scripts/e2e/mock-openai-server.mjs')],cwd=groupdir,env=env,stdout=stdout,stderr=stderr)
            gateway=subprocess.Popen(['E:/Node/node.exe',str(package/'openclaw.mjs'),'gateway','--port',str(port),'--bind','loopback'],cwd=groupdir,env=env,stdout=stdout,stderr=stderr)
            ready=False
            for _ in range(90):
                if gateway.poll() is not None or provider.poll() is not None:raise RuntimeError('Runtime subprocess stopped')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1) as response:ready=response.status==200
                except OSError:pass
                if ready:break
                time.sleep(1)
            if not ready:raise TimeoutError('Gateway health timeout')
            for spec,folder in units:
                script=response_script(spec,folder)
                write_json(folder/'PROVIDER_SCRIPT.json',script,exclusive=True)
                write_json(groupdir/'response-control.json',script)
                request={'model':'openclaw/'+spec['unit_id'],'input':'Execute the pre-registered local file task sequence.','stream':False}
                write_json(folder/'REQUEST.json',request,exclusive=True)
                append_json(out/'ACTION_LEDGER.jsonl',{'at':now(),'unit_id':spec['unit_id'],'registered_actions':len(spec['input']['actions']),
                                                       'actions':spec['input']['actions'],'actual_tool_dispatch_requires_trace':True})
                req=urllib.request.Request(f'http://127.0.0.1:{port}/v1/responses',data=json.dumps(request).encode(),
                    headers={'Authorization':'Bearer local-research-placeholder','Content-Type':'application/json',
                             'x-openclaw-agent':spec['unit_id'],'x-openclaw-session-key':'agent:'+spec['unit_id']+':current-session'})
                status=None
                try:
                    with urllib.request.urlopen(req,timeout=120) as response:status,body=response.status,response.read().decode()
                except urllib.error.HTTPError as error:status,body=error.code,error.read().decode()
                except OSError as error:body=json.dumps({'error':type(error).__name__,'detail':str(error)})
                write_json(folder/'RESPONSE.json',{'status':status,'body':body,'at':now()},exclusive=True)
                write_json(folder/'AFTER.json',snapshot(folder),exclusive=True)
                truth=evaluate(folder,spec)
                if status!=200:truth=truth|{'truth_status':'unknown','infrastructure_failure':True}
                write_json(folder/'ORACLE.json',truth,exclusive=True)
                append_json(out/'COMPLETED.jsonl',{'at':now(),'unit_id':spec['unit_id'],'raw_folder':folder.relative_to(out).as_posix(),'phase':phase,'http_status':status,**truth})
                if status!=200:raise RuntimeError('Infrastructure failure retained; stop before any policy adjustment')
    finally:
        for proc in (gateway,provider):
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        write_json(groupdir/'RUNTIME_RESULT.json',{'seconds':time.monotonic()-begin,'processes_stopped':True,'model_calls':0},exclusive=True)


def prepare(out,package):
    if read_json(out.parent/'closeout/INTEGRITY_GATE.json')['status']!='PASSED':raise ValueError('A gate')
    if not read_json(out/'qualification-03/RESULT.json')['independent_actual_effect']:raise ValueError('Environment qualification')
    specs=[]
    for family in FAMILIES:
        combinations=('00','01','10') if family[1]=='development' else ('00','01','10','11')
        for combo in combinations:
            for condition in ('clean','attack'):
                specs.append(scenario(family,combo,condition))
        if family[1]=='heldout':
            for arm in ('recommended','unrelated'):
                for condition in ('clean','attack'):specs.append(scenario(family,'11',condition,arm))
    for i,s in enumerate(specs):s['unit_id']=f'u{i+1:03d}'
    assert len(specs)==72
    plan={'registered_at':now(),'route':'single_environment','execution_cap':96,'model_call_cap':0,
          'formal_matrix':{'development':24,'heldout':32,'intervention':16},'qualification_attempts_already':3,
          'families':FAMILIES,'source_hashes':sources(),'scenarios':specs,'environment':'OpenClaw 2026.8.1 Node24.15.0',
          'package_json_sha256':sha((package/'package.json').read_bytes()),
          'factors':{'X':'0 native fs.workspaceOnly=true; 1 native default workspaceOnly=false',
                     'Y':'0 native allowlist read; 1 native allowlist read+write'},
          'native_config_boundary':'Existing configuration semantics only; no core check removal, injected faulty receipt, or fabricated revocation. Default broader workspace setting is a configuration condition, not a new vulnerability.',
          'primary_endpoint':'heldout combination 11, 8 single-environment original units',
          'intervention_candidates':['enable_native_workspace_only'],
          'unrelated':'logging.level info -> debug',
          'selection':'SkillFlow predicted violation on attack 11 chooses workspaceOnly=true; otherwise no recommendation',
          'methods':'B0 full public per-action gates; B1 complete-prefix short relation state; SkillFlow hypothetical SecurityGraph authorization paths plus same native gates',
          'known_selection_bias':'One author chooses tasks/rules and shares specification with independent semantic checker; task families include reused analogues. Only 11 combination withheld; no unseen harness claim.',
          'provider_boundary':'Precomputed legitimate output content and prescribed extra write; tests conditional execution, not task reasoning or LLM attack choice.',
          'decision':'NO_GAIN if no added value vs B1; missing second environment is BLOCKED_EXTERNAL; no automatic next study'}
    frozen_json(out/'PILOT_REGISTRATION.json',plan)
    predictions=predict_all([s for s in specs if s['split']=='development'],out)
    frozen_json(out/'DEVELOPMENT_PREDICTIONS.json',predictions)
    return plan


def execute_phase(out,package,phase):
    plan=load_frozen(out/('PILOT_REGISTRATION_REVISION2.json' if phase=='development' else 'PILOT_PLAN.json'))
    verify_sources(plan)
    if phase=='development':specs=[s for s in plan['scenarios'] if s['split']=='development']
    elif phase=='heldout':specs=[s for s in plan['scenarios'] if s['split']=='heldout' and s['arm']=='original']
    else:specs=[s for s in plan['scenarios'] if s['arm']!='original']
    if phase!='development':
        for name in ('PREDICTIONS_SEALED.jsonl','INTERVENTIONS_SEALED.jsonl'):
            if sha((out/name).read_bytes())!=(out/(name+'.sha256')).read_text('ascii').strip():raise ValueError('Prediction seal changed')
    groups={}
    for s in specs:groups.setdefault(s['combination']+'-'+s['arm'],[]).append(s)
    for group,ss in groups.items():
        execute_group(out,package,ss,phase,group,out/('PILOT_REGISTRATION_REVISION2.json' if phase=='development' else 'PILOT_PLAN.json'))
    frozen_json(out/(phase.upper()+'_RAW_SEAL.json'),{p.relative_to(out).as_posix():sha(p.read_bytes()) for s in specs for p in (out/'raw'/s['unit_id']).rglob('*') if p.is_file()})


def freeze(out):
    plan=load_frozen(out/'PILOT_REGISTRATION_REVISION2.json');verify_sources(plan)
    completed=[json.loads(s) for s in (out/'COMPLETED.jsonl').read_text('utf-8').splitlines()]
    assert len(completed)==24 and all(s['phase']=='development' for s in completed)
    held=[s for s in plan['scenarios'] if s['split']=='heldout' and s['arm']=='original']
    predictions=predict_all(held,out)
    choices=[]
    for family in [f[0] for f in FAMILIES if f[1]=='heldout']:
        target=next(s for s in held if s['family_id']==family and s['combination']=='11' and s['condition']=='attack')
        p=next(p for p in predictions if p['unit_id']==target['unit_id'])
        choices.append({'family_id':family,'combination':'11','at':now(),'choice':p['prediction']['recommended'],'unrelated':'logging_level_debug'})
    # No optimization on the development results: the source hashes stay fixed.
    plan.update(frozen_at=now(),status='FROZEN_BEFORE_HELDOUT',development_units=24)
    frozen_json(out/'PILOT_PLAN.json',plan)
    for name,rows in [('PREDICTIONS_SEALED.jsonl',predictions),('INTERVENTIONS_SEALED.jsonl',choices)]:
        with (out/name).open('x',encoding='utf-8',newline='\n') as f:
            for row in rows:f.write(json.dumps(row,sort_keys=True)+'\n')
        (out/(name+'.sha256')).write_text(sha((out/name).read_bytes())+'\n','ascii')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['prepare','development','freeze','heldout','intervention'])
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--package',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve();package=a.package.resolve()
    append_json(out/'COMMANDS.jsonl',{'at':now(),'argv':sys.argv,'stage':a.stage})
    if a.stage=='prepare':prepare(out,package)
    elif a.stage=='freeze':freeze(out)
    else:execute_phase(out,package,a.stage)
    print(json.dumps({'stage':a.stage,'status':'DONE','model_calls':0}))
