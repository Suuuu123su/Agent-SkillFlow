"""Host-only OpenAI Responses transport. No tool execution, retry or fallback."""
import collections
import copy
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent
MODEL = 'gpt-5.6-luna'
ENDPOINT = 'https://api.openai.com/v1/responses'
CAP = 4096  # New Evidence arm total, all roles and diagnostics.

class StopCampaign(BaseException):
    pass

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode('utf-8')).hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def rows(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()] if path.exists() else []

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.writing')
    payload = json.dumps(value, ensure_ascii=False, indent=2)
    last_error = None
    for attempt in range(8):
        try:
            temp.write_text(payload, encoding='utf-8')
            temp.replace(path)
            return
        except PermissionError as error:
            last_error = error
            time.sleep(0.05 * (attempt + 1))
    raise last_error

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise StopCampaign('provider_redirect_refused')

class Provider:
    def __init__(self, key):
        self.key = key
        self.raw = ROOT/'raw'
        self.raw.mkdir(exist_ok=True)
        self.attempts = len(rows(self.raw/'attempts.jsonl'))
        self.access_attempts = sum(read(p).get('request_attempts', 0) for p in ROOT.glob('MODEL_ACCESS_CHECK*.json'))
        self.tokens = sum(x.get('response', {}).get('usage', {}).get('total_tokens', 0) for x in rows(self.raw/'results.jsonl'))
        self.counts = collections.Counter((x['unit'],x['role']) for x in rows(self.raw/'attempts.jsonl'))
        self.hook = lambda **kw: None

    def append(self, name, value):
        text = canonical(value)
        if self.key:
            text = text.replace(self.key, '[REDACTED]')
        with (self.raw/name).open('a', encoding='utf-8') as f:
            f.write(text+'\n')

    def create(self, unit, role, body):
        if (ROOT/'PAUSE_REQUEST.json').exists() and read(ROOT/'PAUSE_REQUEST.json').get('active'):
            raise StopCampaign('user_pause_requested')
        if (ROOT/'STOP_ATTACK.json').exists():raise StopCampaign('campaign_stopped')
        if not unit.startswith(('cs_delay_','cs_frag_','cs_mem_')):raise StopCampaign('non_attack_unit_forbidden')
        if sha((ROOT/'STOP_REPAIR3.json').read_bytes())!=read(ROOT/'ATTACK_CHECKPOINT.json')['old_stop_sha256']:raise StopCampaign('prior_stop_changed')
        if self.attempts+self.access_attempts >= CAP:
            raise StopCampaign('request_cap')
        assert role in {'actor','judge','defense','diagnostic'}
        if role in {'actor','judge'} and self.counts[unit,role] >= (20 if role=='actor' else 1):
            raise StopCampaign('per_unit_request_cap')
        if role=='defense' and self.counts[unit,role]>=256:raise StopCampaign('per_unit_defense_request_cap')
        assert body['model']==MODEL and body['store'] is False
        assert body['max_output_tokens']==8192
        raw=canonical(body)
        if not self.key or self.key in raw:
            raise StopCampaign('credential_payload_guard')
        self.attempts+=1
        self.counts[unit,role]+=1
        aid=self.attempts
        self.append('attempts.jsonl',{'id':aid,'unit':unit,'role':role,'endpoint':ENDPOINT,
                                    'request':body,'request_sha256':sha(raw),'time':time.time()})
        self.hook(inflight=True,unit=unit,role=role)
        started=time.monotonic()
        try:
            req=Request(ENDPOINT,data=raw.encode('utf-8'),headers={'Content-Type':'application/json','Authorization':'Bearer '+self.key},method='POST')
            with build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=240) as res:
                response=json.loads(res.read())
        except HTTPError as error:
            record={'id':aid,'http_status':error.code,'elapsed_s':time.monotonic()-started}
            try:
                value=json.loads(error.read()).get('error',{})
                record.update({k:value.get(k) for k in ('type','code','param')})
            except Exception:
                pass
            self.append('results.jsonl',record)
            raise StopCampaign('provider_http_'+str(error.code))
        except StopCampaign:
            self.append('results.jsonl',{'id':aid,'error_type':'redirect_refused'})
            raise
        except Exception as error:
            self.append('results.jsonl',{'id':aid,'error_type':type(error).__name__,'cause_type':type(getattr(error,'reason',None)).__name__,'errno':getattr(getattr(error,'reason',None),'errno',None),'elapsed_s':time.monotonic()-started,'unknown_delivery':True})
            raise StopCampaign('transport_unknown_delivery_no_retry')
        finally:
            self.hook(inflight=False,unit=unit,role=role)
        response=json.loads(canonical(response).replace(self.key,'[REDACTED]'))
        self.append('results.jsonl',{'id':aid,'http_status':200,'elapsed_s':time.monotonic()-started,'response':response})
        self.tokens+=response.get('usage',{}).get('total_tokens',0)
        if not re.fullmatch(re.escape(MODEL)+r'(?:-\d{4}-\d{2}-\d{2})?',response.get('model','')):
            raise StopCampaign('response_model_mismatch')
        if response.get('error'):
            raise StopCampaign('response_error')
        if response.get('status') not in {'completed','incomplete'}:
            raise StopCampaign('unexpected_response_status')
        if response.get('status')=='incomplete' and (response.get('incomplete_details') or {}).get('reason')!='max_output_tokens':
            raise StopCampaign('provider_restriction_or_incomplete')
        for item in response.get('output',[]):
            if item.get('type') not in {'reasoning','message','function_call'}:
                raise StopCampaign('unexpected_output_item')
            if any(c.get('type')=='refusal' for c in item.get('content',[]) or []):
                raise StopCampaign('provider_refusal')
        self.hook(inflight=False,unit=unit,role=role)
        return response

    def clear(self):
        self.key=''

def convert_messages(messages):
    out=[]
    for message in messages:
        role=message['role']
        if role=='tool':
            out.append({'type':'function_call_output','call_id':message['tool_call_id'],'output':message['content']})
        elif role=='assistant' and message.get('tool_calls'):
            if message.get('content'):
                out.append({'role':'assistant','content':message['content']})
            for call in message['tool_calls']:
                out.append({'type':'function_call','call_id':call['id'],'name':call['function']['name'],'arguments':call['function']['arguments']})
        else:
            assert role in {'system','developer','user','assistant'}
            out.append({'role':role,'content':message.get('content') or ''})
    return out

def base_body(input_items):
    return {'model':MODEL,'input':input_items,'store':False,'max_output_tokens':8192,
            'reasoning':{'effort':'medium'},'include':['reasoning.encrypted_content']}

def output_text(response):
    return ''.join(c.get('text','') for item in response.get('output',[]) if item['type']=='message'
                   for c in item.get('content',[]) if c.get('type')=='output_text')

class Actor:
    def __init__(self,provider,unit,role='actor',first_check=None):
        self.provider=provider;self.unit=unit;self.role=role;self.first_check=first_check
        self.prior_messages=None;self.raw_history=[];self.projected=None;self.system=None

    def chat(self,system,tools,messages):
        from agent_eval.sandbox.agent_loop import ConversationTurn,_build_assistant_message_openai
        if self.prior_messages is None:
            self.system=system
            if self.first_check:self.first_check(system,tools,messages)
            inputs=convert_messages([{'role':'system','content':system}]+messages)
        else:
            assert system==self.system,'system_changed'
            expected=self.prior_messages+[self.projected]
            assert messages[:len(expected)]==expected,'native_history_changed'
            inputs=copy.deepcopy(self.raw_history)+convert_messages(messages[len(expected):])
        body=base_body(inputs)
        if tools:
            body['tools']=[{'type':'function','name':t['name'],'description':t.get('description',''),
                            'parameters':copy.deepcopy(t.get('parameters',{'type':'object','properties':{}})),
                            'strict':False} for t in tools]
        response=self.provider.create(self.unit,self.role,body)
        calls=[]
        for item in response.get('output',[]):
            if item['type']=='function_call':
                try:args=json.loads(item['arguments'])
                except (ValueError,TypeError):args={'raw':item['arguments']}
                calls.append({'id':item['call_id'],'name':item['name'],'input':args})
        text=output_text(response)
        if not calls and not text.strip() and response['status']=='completed':
            raise StopCampaign('empty_completed_response')
        turn=ConversationTurn(text_content=text,tool_calls=calls,
                              stop_reason='tool_use' if calls else ('max_tokens' if response['status']=='incomplete' else 'end_turn'))
        self.prior_messages=copy.deepcopy(messages)
        self.projected=_build_assistant_message_openai(turn)
        self.raw_history=inputs+copy.deepcopy(response['output'])
        return turn

class JudgeClient:
    def __init__(self,provider,unit,expected):
        self.provider=provider;self.unit=unit;self.expected=expected

    def complete(self,system,user):
        from judge_validation import validate_judge_response
        messages=[{'role':'system','content':system},{'role':'user','content':user}]
        assert messages==self.expected,'native_judge_prompt_changed'
        body=base_body(convert_messages(messages))
        body['text']={'format':{'type':'json_object'}}
        response=self.provider.create(self.unit,'judge',body)
        choice={'finish_reason':'stop' if response['status']=='completed' else 'length',
                'message':{'content':output_text(response)}}
        try:return validate_judge_response(choice)
        except Exception:raise StopCampaign('invalid_native_judge_response')
