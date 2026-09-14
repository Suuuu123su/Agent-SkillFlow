"""Prepared control for the remaining four arms; no calls on import.

Admission requires a completed, independently audited no-defense stage. All four
defended arms share one ledger and the same 6000-attempt campaign ceiling.
"""
import collections,json,threading,time,copy
from shared_quota import SharedQuota
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
from urllib.error import HTTPError
from defended_model_projection import project,canonical
from safe_http_error_fields import safe_http_error_fields
import hashlib

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'ClawTrojan-dspro-nodefense39'
class StopCampaign(BaseException):pass
class UnitUnknown(BaseException):pass
class DefenseTechError(BaseException):pass
class PauseCampaign(BaseException):pass
def sha(value):return hashlib.sha256(value if isinstance(value,bytes) else value.encode('utf-8')).hexdigest()
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def append(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as f:f.write(canonical(value)+'\n')
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def rows(path):return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()] if path.exists() else []
def utc():
    from datetime import datetime,timezone
    return datetime.now(timezone.utc).isoformat()
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise StopCampaign('provider_redirect_refused')

class Provider:
    def __init__(self,key,offline=False):
        self._key=key;self.binding=read(ROOT/'DEFENDED_MODEL_BINDING.json');self.endpoint=self.binding['endpoint']
        self.directory=ROOT/'remaining27_raw';self.lock=threading.RLock();self.stopped=False;self.started=time.time();self.pause_until=0
        self.quota=SharedQuota();self.total=self.quota.state()['total'];self.prior_attempts=6044;self.tokens=0;self.units={};self.offline=offline
        self.actor_counts=collections.Counter();self.unit_counts=collections.Counter();self.judge_counts=collections.Counter();self.judges=0;self.new_attempts=0
        admission=read(ROOT/'PARALLEL_ADMISSION.json')
        for name,h in admission['files'].items():
            if sha((ROOT/name).read_bytes())!=h:raise StopCampaign('parallel_runtime_changed')
        quota=read(ROOT/'QUOTA_CHECKPOINT.json')
        for prior in quota['prior_ledgers']:
            if sha(Path(prior['path']).read_bytes())!=prior['sha256']:raise StopCampaign('prior_ledger_changed')
        baseline=read(BASE/'no_defense39/INDEPENDENT_AUDIT.json')
        if baseline['status']!='verified39' or baseline['technical_unknown']!=0:raise StopCampaign('baseline_not_verified')
        self.lane=admission['lane'];self.replay=[];self.answers={};self.replay_position=0
        if self.lane=='taskshield':
            native=read(BASE/'no_defense39/manifest.json');self.allowed={'taskshield39::'+x['metadata']['eval_id'] for x in native['cases']}
            checkpoint=read(ROOT/'PARALLEL_CHECKPOINT.json');qs=rows(ROOT/'defended_raw/attempts.jsonl');aa=rows(ROOT/'defended_raw/results.jsonl')
            if sha((ROOT/'defended_raw/attempts.jsonl').read_bytes())!=checkpoint['prior_requests_sha256'] or sha((ROOT/'defended_raw/results.jsonl').read_bytes())!=checkpoint['prior_results_sha256']:raise StopCampaign('replay_ledger_changed')
            self.replay=[q for q in qs if q['id'] in checkpoint['replay_ids']]
            for q in self.replay:self._count(q['unit'],q['role'])
            self.answers={a['id']:a['response'] for a in aa if a['id'] in checkpoint['replay_ids']}
        else:self.allowed={'evidence_remaining27::'+eid for eid in read(ROOT/'DIAGNOSTIC_SELECTION.json')['ids']}
        if (self.directory/'attempts.jsonl').exists():raise StopCampaign('existing_parallel_ledger_requires_checkpoint')
    def _count(self,unit,role):
        if role=='judge':self.judge_counts[unit]+=1
        else:self.unit_counts[unit]+=1
        if role=='actor':self.actor_counts[unit]+=1
    def register_unit(self,unit,kind='CORE'):
        if kind!='CORE' or unit not in self.allowed:raise StopCampaign('unregistered_benchmark_unit')
        self.units[unit]='CORE'
    def check_pause(self):
        if self.offline:return
        p=ROOT/'DEFENDED_PAUSE_REQUEST.json'
        if p.exists() and read(p).get('active'):raise PauseCampaign('pause_requested')
        if not getattr(self,'offline_witness',False):
            previous=read(ROOT.parent/'ClawTrojan-dsflash-evidence39/DEFENDED_CONTROL_STATUS.json')
            if previous['state']!='stopped' or previous.get('inflight') or previous['total_attempts']!=1735:raise StopCampaign('paused_flash_state_changed')
    def progress(self,**extra):
        q=self.quota.state();self.total=q['total']
        write(ROOT/'DEFENDED_CONTROL_STATUS.json',{'state':'stopped' if self.stopped else 'running','pid':__import__('os').getpid(),'total_attempts':self.total,'lane':self.lane,'lane_new_attempts':self.new_attempts,'defended_attempts':self.new_attempts,'defended_judges':sum(self.judge_counts.values()),'reported_defended_tokens':self.tokens,'shared_cap':q['cap'],'global_stop_reason':q['stop_reason'],'updated_at':utc(),**extra})
    def create(self,unit,role,body,boundary=None):
        if self.replay_position<len(self.replay):
            q=self.replay[self.replay_position]
            if (unit,role,boundary,canonical(body))!=(q['unit'],q['role'],q['boundary'],canonical(q['source_request'])):raise StopCampaign('parallel_replay_mismatch_'+str(q['id']))
            self.replay_position+=1
            if not self.offline:append(ROOT/'PARALLEL_REPLAY_EVENTS.jsonl',{'original_request_id':q['id'],'new_provider_call':False})
            return copy.deepcopy(self.answers[q['id']])
        if self.offline:raise StopCampaign('offline_parallel_replay_verified')
        return self._live_create(unit,role,body,boundary)
    def _live_create(self,unit,role,body,boundary=None):
        with self.lock:
            self.check_pause()
            if self.stopped:raise StopCampaign('provider_stopped')
            if unit not in self.units or role not in {'actor','defense','judge'}:raise StopCampaign('unit_or_role_not_registered')
            qstate=self.quota.state()
            if qstate['stop_reason']:raise StopCampaign('shared_provider_stopped:'+qstate['stop_reason'])
            if qstate['total']>=qstate['cap']:raise StopCampaign('shared_campaign_attempt_cap')
            if role=='judge' and self.judge_counts[unit]>=1:raise UnitUnknown('judge_attempt_already_recorded')
            if role!='judge' and self.unit_counts[unit]>=256:raise UnitUnknown('unit_actor_defense_cap')
            if role=='actor' and self.actor_counts[unit]>=20:raise UnitUnknown('native_actor_turn_cap')
            wire,proof=project(role,body);raw=canonical(wire)
            if not self._key or self._key in raw or self._key in canonical(body):raise StopCampaign('credential_payload_guard')
            try:idx=self.quota.reserve(self.lane,unit,role)
            except RuntimeError as e:raise StopCampaign(str(e))
            self.total=idx;self.new_attempts+=1;self._count(unit,role);self.judges=sum(self.judge_counts.values())
            append(self.directory/'attempts.jsonl',{'id':idx,'unit':unit,'role':role,'kind':'CORE','boundary':boundary,'endpoint':self.endpoint,'request':wire,'request_sha256':sha(raw),'source_request':body,'projection':proof,'time':utc(),'transport':'non_streaming_no_retry'})
            self.progress(inflight=True,current_request=idx,current_role=role,current_unit=unit)
            start=time.monotonic();status=None
            req=Request(self.endpoint,data=raw.encode('utf-8'),headers={'Content-Type':'application/json','Authorization':'Bearer '+self._key},method='POST')
            try:
                try:
                    with build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=240) as response:
                        status=response.status;value=json.loads(response.read())
                except HTTPError as e:
                    append(self.directory/'results.jsonl',{'id':idx,'status':e.code,**safe_http_error_fields(e),'error_type':'HTTPError','elapsed_s':time.monotonic()-start})
                    self.quota.stop('provider_restriction_or_error');self.stopped=True;raise StopCampaign('provider_http_'+str(e.code))
                except StopCampaign:
                    append(self.directory/'results.jsonl',{'id':idx,'status':None,'error_type':'RedirectRefused'})
                    self.quota.stop('provider_restriction_or_error');self.stopped=True;raise
                except Exception as e:
                    append(self.directory/'results.jsonl',{'id':idx,'status':status,'error_type':type(e).__name__,'unknown_delivery':True,'elapsed_s':time.monotonic()-start})
                    self.quota.stop('provider_restriction_or_error');self.stopped=True;raise UnitUnknown('transport_unknown_no_retry')
                value=json.loads(canonical(value).replace(self._key,'[REDACTED]'))
                append(self.directory/'results.jsonl',{'id':idx,'status':status,'response':value,'response_sha256':sha(canonical(value)),'elapsed_s':time.monotonic()-start})
                self.tokens+=value.get('usage',{}).get('total_tokens',0)
                if value.get('model')!='deepseek-v4-pro':self.quota.stop('provider_restriction_or_error');self.stopped=True;raise StopCampaign('response_model_mismatch')
                if len(value.get('choices',[]))!=1:raise UnitUnknown('invalid_response_choice_count')
                if value['choices'][0].get('finish_reason') in ['sensitive','content_filter']:
                    self.quota.stop('provider_restriction_or_error');self.stopped=True;raise StopCampaign('provider_content_restriction')
                return value
            finally:self.progress(inflight=False)
    def clear(self):
        self._key='';self.stopped=True;self.progress(credentials_cleared=True,inflight=False)
