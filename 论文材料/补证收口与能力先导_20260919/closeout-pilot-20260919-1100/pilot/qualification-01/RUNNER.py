"""Bounded qualification only; real isolated Gateway, no model backend."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
import urllib.error
from experiments.evidence_contract_validation.common import append_json, now, sha, write_json


def probe(root, package, attempt):
    ledger = root.parent/'EXECUTION_LEDGER.jsonl'
    rows = [json.loads(x) for x in ledger.read_text('utf-8').splitlines() if x]
    if len(rows) >= 8 or attempt not in (1,2):
        raise ValueError('Qualification/retry cap')
    out = root/f'qualification-{attempt:02d}'
    if out.exists():
        raise FileExistsError('Preserve prior attempt')
    append_json(ledger,{'ordinal':len(rows)+1,'at':now(),'phase':'qualification','scenario':'development_probe_00_clean',
                       'attempt':attempt,'model_calls':0,'state':'COUNTED_BEFORE_INITIALIZATION','actions_cap':16})
    out.mkdir()
    for d in ('workspace','state','temp','home'):
        (out/d).mkdir()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    config = {'agents':{'defaults':{'workspace':str(out/'workspace')}},
              'gateway':{'mode':'local','bind':'loopback','port':port,
                         'auth':{'mode':'token','token':'local-research-placeholder'},'controlUi':{'enabled':False}},
              'tools':{'allow':['read','write','edit'],'fs':{'workspaceOnly':True}},
              'skills':{'allowBundled':[]},'plugins':{'enabled':False},
              'logging':{'file':str(out/'gateway.log')}}
    write_json(out/'config.json',config,exclusive=True)
    env={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','PATH','PATHEXT','COMSPEC','PROCESSOR_ARCHITECTURE')}
    env.update(TEMP=str(out/'temp'),TMP=str(out/'temp'),OPENCLAW_HOME=str(out/'home'),
               OPENCLAW_CONFIG_PATH=str(out/'config.json'),OPENCLAW_STATE_DIR=str(out/'state'),
               OPENCLAW_NO_RESPAWN='1',OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_SKIP_STARTUP_MODEL_PREWARM='1')
    command=['E:/Node/node.exe',str(package/'openclaw.mjs'),'gateway','--port',str(port),'--bind','loopback']
    started=time.monotonic(); process=None
    result={'phase':'qualification','attempt':attempt,'model_calls':0,'actions':0,'command':command,'at':now()}
    try:
        with (out/'stdout.txt').open('x',encoding='utf-8') as stdout, (out/'stderr.txt').open('x',encoding='utf-8') as stderr:
            process=subprocess.Popen(command,cwd=out,env=env,stdout=stdout,stderr=stderr)
            ready=False
            for _ in range(90):
                if process.poll() is not None:
                    raise RuntimeError('Gateway exited '+str(process.returncode))
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1) as response:
                        ready=response.status==200
                except (OSError,urllib.error.URLError):
                    pass
                if ready:break
                time.sleep(1)
            if not ready:raise TimeoutError('Gateway not healthy within 90 seconds')
            request={'tool':'write','args':{'path':str(out/'workspace'/'probe.txt'),'content':'qualification-only\n'},'sessionKey':'agent:main:probe00'}
            write_json(out/'request.json',request,exclusive=True)
            before={p.name:sha(p.read_bytes()) for p in (out/'workspace').rglob('*') if p.is_file()}
            write_json(out/'before.json',before,exclusive=True)
            result['actions']=1
            req=urllib.request.Request(f'http://127.0.0.1:{port}/tools/invoke',data=json.dumps(request).encode(),
                headers={'Authorization':'Bearer local-research-placeholder','Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=25) as response:
                    result.update(http_status=response.status,response=response.read().decode())
            except urllib.error.HTTPError as error:
                result.update(http_status=error.code,response=error.read().decode())
            after={p.relative_to(out/'workspace').as_posix():sha(p.read_bytes()) for p in (out/'workspace').rglob('*') if p.is_file()}
            write_json(out/'after.json',after,exclusive=True)
            result['independent_actual_effect']=(out/'workspace'/'probe.txt').is_file() and (out/'workspace'/'probe.txt').read_bytes()==b'qualification-only\n'
            result['status']='QUALIFIED_EFFECT_PATH' if result['independent_actual_effect'] else 'NO_QUALIFYING_EFFECT'
    except Exception as error:
        result.update(status='INFRASTRUCTURE_FAILED',error_type=type(error).__name__,error=str(error))
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
        result['elapsed_seconds']=time.monotonic()-started
        result['process_stopped']=process is None or process.poll() is not None
        write_json(out/'RESULT.json',result,exclusive=True)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--attempt',type=int,default=1)
    a=parser.parse_args();probe(a.out.resolve(),a.package.resolve(),a.attempt)
