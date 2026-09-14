"""Prepared native39 driver for original frozen defenses; not yet admitted.
No API call unless --run is explicit and the audited prerequisite gates pass.
"""
import argparse,collections,copy,importlib,importlib.util,inspect,json,sys,time,types
from dataclasses import asdict
from pathlib import Path
import parallel_provider as control
from parallel_provider import ROOT,read,write,append,sha,StopCampaign,UnitUnknown,DefenseTechError

MODEL='deepseek-v4-pro'
ARMS=('evidence',)
def family(arm):return 'components' if arm in ('content','derived') else arm
def hashes(path):return {p.relative_to(path).as_posix():sha(p.read_bytes()) for p in sorted(path.rglob('*')) if p.is_file()}
def bootstrap(arm):
    for name in list(sys.modules):
        if any(name==p or name.startswith(p+'.') for p in ('agent_eval','claw_trojan','evidence_method','evidence_engine','evidence_adapter','semantic_review','skillflow','taskshield_adapter')):del sys.modules[name]
    up=ROOT/'defended_native_snapshot';method=ROOT/'defense_source_snapshots'/family(arm)
    sys.path[:0]=[str(up),str(method/'method'),str(method)]
    sys.modules['provider_session']=control
    for name in ['agent_eval','agent_eval.sandbox']:
        module=types.ModuleType(name);module.__path__=[str(up.joinpath(*name.split('.')))];sys.modules[name]=module
    importlib.invalidate_caches()
    from loguru import logger
    logger.remove()
    from agent_eval.sandbox import runner
    assert 'evidence_factory' in inspect.signature(runner.SandboxRunner).parameters
    if arm=='taskshield':
        from taskshield_adapter import ContractAdapter
        return runner,ContractAdapter,None
    from evidence_engine import EvidenceEngine
    from evidence_adapter import EvidenceAdapter
    assert ('component' in inspect.signature(EvidenceEngine).parameters)==(arm in ('content','derived'))
    return runner,EvidenceEngine,EvidenceAdapter

def verify_sources(arm):
    native=read(ROOT/'DEFENDED_NATIVE_SOURCE_PROOF.json')
    for name,h in native['files'].items():assert sha((ROOT/'defended_native_snapshot'/name).read_bytes())==h,name
    sources=read(ROOT/'defense_source_snapshots/SOURCE_VERIFICATION.json')[family(arm)]['files']
    for name,h in sources.items():assert sha((ROOT/'defense_source_snapshots'/family(arm)/name).read_bytes())==h,name

def inspect_stage(arm):
    verify_sources(arm);runner,cls,adapter=bootstrap(arm)
    result={'arm':arm,'original_method_imported':True,'native_Evidence_hook_available':True,'single_component_parameter':arm in ('content','derived'),'API_calls':0,'live_hook_witness':'pending','full_runtime_admitted':False}
    write(ROOT/('DEFENDED_IMPORT_'+arm+'.json'),result)
    return result

def run(provider,arm):
    verify_sources(arm)
    admission=read(ROOT/'DEFENDED_RUNTIME_ADMISSION.json')
    if admission.get('status')!='admitted':raise StopCampaign('runtime_not_admitted')
    for name,h in admission['runtime_files'].items():
        if sha((ROOT/name).read_bytes())!=h:raise StopCampaign('runtime_freeze_changed')
    nr,Defense,Adapter=bootstrap(arm)
    from openai.types.chat import ChatCompletion
    from agent_eval.sandbox.agent_loop import OpenAIToolUseClient
    from agent_eval.sandbox.schema import SandboxConfig,ToolMock,AgentTrace,JudgeVerdict
    from agent_eval.sandbox.asr_judge import ASRJudge
    from agent_eval.sandbox.sandbox_eval import _extract_tainted_artifacts
    from agent_eval.sandbox.sandbox_metrics import compute_sandbox_metrics
    from judge_validation import validate_judge_response
    source_root=ROOT/'defense_source_snapshots'/family(arm)
    manifest=read(source_root/'control_reference/BASELINE39_MANIFEST.json')
    order=read(ROOT/'DIAGNOSTIC_SELECTION.json')['ids']
    lookup={x['metadata']['eval_id']:x for x in manifest['cases']}
    out=ROOT/'defended_runs'/(arm+'_remaining27');out.mkdir(parents=True,exist_ok=True)
    if (out/'targets_started.jsonl').exists():raise StopCampaign('existing_stage_requires_registered_checkpoint')
    contracts=read(source_root/'CONTRACT_INDEX.json') if arm=='taskshield' else None
    verdicts=[];metas=[];taints=collections.defaultdict(list);state='running';reason=None
    def status():write(out/'STATUS.json',{'state':state,'completed':len(verdicts),'planned':len(order),'unknown':sum(v.verdict=='error' for v in verdicts),'reason':reason,'pid':__import__('os').getpid(),'time':control.utc()})
    class JudgeClient:
        def __init__(self,unit):self.unit=unit
        def complete(self,system,user):
            body=copy.deepcopy(provider.binding['models']['judge']['request_parameters']);body['messages']=[{'role':'system','content':system},{'role':'user','content':user}]
            value=provider.create(self.unit,'judge',body)
            return validate_judge_response(value['choices'][0])
    native_dispatcher=nr.ToolDispatcher
    try:
        for index,eid in enumerate(order):
            provider.check_pause();item=lookup[eid];meta=item['metadata'];c=copy.deepcopy(item['config'])
            taints[meta['sample_id']]=copy.deepcopy(read(ROOT/'HOST_ONLY_ORIGINAL_JUDGE_CONTEXTS.json')[eid]['prior_tainted_artifacts'])
            c['max_turns']=20
            public={k:c[k] for k in ('system_prompt','session_history','user_input','available_tools','max_turns')}
            relative=Path(c['workspace_path']).relative_to(Path(manifest['baseline_root'])/'upstream')
            source=ROOT/'defended_native_snapshot'/relative
            assert hashes(source)=={k.replace('\\','/'):v for k,v in item['initial_workspace_files'].items()}
            c['workspace_path']=str(source);c['tool_mocks']=[ToolMock(**x) for x in c['tool_mocks']];config=SandboxConfig(**c)
            tools=[{'type':'function','function':t} for t in nr._build_tool_defs(public['available_tools'])]
            assert tools==item['actual_actor_tools']
            initial=[{'role':'system','content':public['system_prompt']}]+copy.deepcopy(public['session_history'])
            if not(initial and initial[-1].get('role')=='user' and str(initial[-1].get('content','')).strip()==public['user_input'].strip()):initial.append({'role':'user','content':public['user_input']})
            assert initial==item['first_actor_request_messages']
            unit=arm+'_remaining27::'+eid;provider.register_unit(unit)
            case=out/eid;case.mkdir(exist_ok=False);objects={};start=time.monotonic()
            append(out/'targets_started.jsonl',{'eval_id':eid,'index':index,'time':control.utc()});status()
            class Retained:
                def __init__(self,*args,**kwargs):self.path=case/'sandbox';self.path.mkdir(exist_ok=False)
                def __enter__(self):return str(self.path)
                def __exit__(self,*args):return False
            class Facade:
                def __init__(self):self.chat=types.SimpleNamespace(completions=self)
                def create(self,**body):return ChatCompletion.model_validate(provider.create(unit,'actor',body))
            actor=OpenAIToolUseClient.__new__(OpenAIToolUseClient);actor.model=MODEL;actor.client=Facade()
            nr.create_tool_use_client=lambda *a,**kw:actor;nr.tempfile.TemporaryDirectory=Retained;nr.ToolDispatcher=native_dispatcher
            kwargs={};baseline='no_defense'
            if arm=='taskshield':
                contract=read(source_root/contracts[eid]);assert contract['legal_request_sha256']==sha(public['user_input'])
                gate=Defense(contract,case/'gate_events.jsonl')
                class GatedDispatcher(native_dispatcher):
                    def __init__(self,*a,**kw):super().__init__(*a,**kw);objects['dispatcher']=self
                    def dispatch(self,name,args):return gate.dispatch(self,name,args,lambda:super(GatedDispatcher,self).dispatch(name,args))
                nr.ToolDispatcher=GatedDispatcher;write(case/'TASK_CONTRACT.json',contract)
            else:
                def factory(workspace,audit):
                    extra={'component':arm} if arm in ('content','derived') else {}
                    engine=Defense(provider,unit,public['user_input'],tools,case/'evidence',**extra)
                    adapter=Adapter(engine,workspace);objects.update(engine=engine,adapter=adapter,audit=audit,workspace=workspace);return adapter
                kwargs['evidence_factory']=factory;baseline='evidence'
            error=None
            try:
                trace,audit,diff=nr.SandboxRunner(config,backend='openai',model=MODEL,baseline=baseline,**kwargs).run_trial(trial=0)
            except (UnitUnknown,DefenseTechError) as e:
                error=str(e);workspace=case/'sandbox/workspace';audit=objects.get('audit',getattr(objects.get('dispatcher'),'audit',[]))
                diff=nr.capture_workspace_diff(source,workspace)
                trace=AgentTrace(eval_id=eid,model=MODEL,trial=0,messages=[],tool_calls=list(audit),final_response='',terminated_reason='error',duration_seconds=time.monotonic()-start,metadata={'technical_error':error})
            finally:
                if 'engine' in objects:write(case/'EVIDENCE_TRACE.json',objects['engine'].export())
                workspace=case/'sandbox/workspace'
                write(case/'WORKSPACE_HASHES.json',{'before':item['initial_workspace_files'],'after':hashes(workspace) if workspace.exists() else {}})
            write(case/'trace.json',trace.to_dict());write(case/'audit.json',[asdict(a) for a in audit]);write(case/'workspace_diff.json',diff)
            write(case/'JUDGE_CONTEXT.json',{'prior_tainted_artifacts':copy.deepcopy(taints[meta['sample_id']]),'is_malicious':meta['is_malicious'],'defense_visibility':False})
            if trace.terminated_reason=='error':
                verdict=JudgeVerdict(eval_id=eid,model=MODEL,trial=0,verdict='error',confidence=0,reasoning='Technical unknown: '+str(error))
            else:
                judge=ASRJudge(JudgeClient(unit))
                verdict=judge.judge(config,trace,diff,taints[meta['sample_id']]) if meta['is_malicious'] else judge.judge_clean(config,trace,diff)
            write(case/'judge.json',verdict.to_dict());verdicts.append(verdict);metas.append(meta)
            append(out/'native_results.jsonl',{'metadata':meta,'verdict':verdict.to_dict(),'termination':trace.terminated_reason,'arm':arm,'actor_requests':provider.actor_counts[unit],'actor_defense_requests':provider.unit_counts[unit],'terminal_error':error})
            if meta['is_malicious']:taints[meta['sample_id']].extend(_extract_tainted_artifacts(diff,verdict,meta['step_idx']))
            write(out/'native_metrics.json',compute_sandbox_metrics(verdicts,metas));status()
            if verdict.verdict=='error':raise StopCampaign('native_technical_unknown_stop')
            print(f'{arm}: {len(verdicts)}/{len(order)} | {eid}={verdict.verdict} | shared requests {provider.total}/6000 | defended tokens {provider.tokens}',flush=True)
        state='complete'
    except BaseException as e:
        state='stopped';reason=str(e) if isinstance(e,(StopCampaign,UnitUnknown,DefenseTechError)) else type(e).__name__;raise
    finally:
        write(out/'native_metrics.json',compute_sandbox_metrics(verdicts,metas));status()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--arm',choices=ARMS,required=True);parser.add_argument('--run',action='store_true');args=parser.parse_args()
    if not args.run:print(json.dumps(inspect_stage(args.arm)));return
    admission=read(ROOT/'DEFENDED_RUNTIME_ADMISSION.json')
    if admission.get('status')!='admitted':raise StopCampaign('runtime_not_admitted')
    path=ROOT/'credential_store.py'
    spec=importlib.util.spec_from_file_location('trusted_credentials',path);credentials=importlib.util.module_from_spec(spec);spec.loader.exec_module(credentials)
    provider=None;key=credentials.load_credential()
    try:provider=control.Provider(key);run(provider,args.arm)
    finally:
        key=''
        if provider is not None:provider.clear()
if __name__=='__main__':main()
