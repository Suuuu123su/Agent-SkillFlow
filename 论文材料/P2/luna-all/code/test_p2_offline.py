import unittest,json,sys,collections,copy,tempfile,threading,http.client,io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'code'));sys.path.insert(0,str(ROOT/'frozen_method'));sys.path.insert(0,str(ROOT/'monitor'))
import p2_transport as p2
sys.modules['responses_transport']=p2
from cli_transport import SendGuard,UPSTREAM_HOST,UPSTREAM_PATH
from http.server import ThreadingHTTPServer
import all_selection
all_selection.install()
from evidence_engine import EvidenceEngine
from evidence_adapter import EvidenceAdapter
from progress_writer import project_snapshot
from runtime_state import State

class FakeState:
 def __init__(self):
  self.lock=threading.RLock();self.u={'unit_id':'TEST','status':'running','actor_turn':0}
  self.value={'requests':{'attempts':0,'settled':0,'in_flight':0,'response_unknown':0,'by_role':{}},'started_at':None}
 def unit(self,uid):return self.u
 def flush(self,*a):pass

def provider():
 p=object.__new__(p2.Provider);p.key=None;p.requires_api_key=False;p.state=FakeState();p.counts=collections.Counter();p.records=[]
 p.append=lambda name,value:p.records.append((name,value))
 return p

def valid_wire():return json.loads((ROOT/'offline_cli/mock_requests.json').read_text(encoding='utf-8'))[0]['body']
def last_prompt(wire):
 c=wire['input'][-1]['content'];return c if isinstance(c,str) else ''.join(x.get('text','') for x in c)

class ScriptedProvider:
 def __init__(self,deny=False):self.boundaries=[];self.deny=deny
 def create(self,unit,role,body,boundary=None):
  self.boundaries.append(boundary)
  if boundary.endswith('dynamic_route'):v={'intent':'literal_reference','source_instruction_present':False,'source_support':[{'span_id':'s1','supports':'data','uncertainty':''}],'reason':'scripted protocol fixture'}
  else:v={'action_scope':'current fixture','candidate_use':'persist_control' if self.deny else 'quote','control_promotion':'supported' if self.deny else 'none','semantic_status':'unsupported' if self.deny else 'supported','decision':'deny_commit' if self.deny else 'retain','source_support':[{'span_id':'s1','supports':'data','uncertainty':''}],'control_span_ids':[],'reason':'scripted protocol fixture','recovery':'Continue within the actual task.' if self.deny else ''}
  return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(v)}}]}

class Tests(unittest.TestCase):
 def test_01_real_cli_empty_tools_and_clean_context(self):
  v=json.loads((ROOT/'offline_cli/ISOLATION_POSITIVE_TEST.json').read_text(encoding='utf-8'))
  self.assertTrue(v['canary_absent']);self.assertTrue(v['builtin_coding_persona_absent']);self.assertEqual(v['wire_tools'],[[]]);self.assertEqual(v['external_provider_requests'],0)
 def test_02_negative_agents_wire_rejected(self):
  w=json.loads((ROOT/'offline_cli/NEGATIVE_WIRE.json').read_text(encoding='utf-8'));g=SendGuard(provider(),'TEST','actor',p2.base_body([]),ROOT,last_prompt(w))
  with self.assertRaisesRegex(ValueError,'HOST_CONTEXT_LEAK'):g.validate(UPSTREAM_PATH,{'x-p2-binding':g.token,'Authorization':'Bearer local-fixture'},json.dumps(w).encode())
 def test_03_final_model_guard(self):
  w=valid_wire();g=SendGuard(provider(),'TEST','actor',p2.base_body([]),ROOT,last_prompt(w));w['model']='glm-5'
  with self.assertRaisesRegex(ValueError,'FINAL_WIRE_MODEL_NOT_LUNA'):g.validate(UPSTREAM_PATH,{'x-p2-binding':g.token,'Authorization':'Bearer local-fixture'},json.dumps(w).encode())
 def test_04_route_and_host_tools(self):
  w=valid_wire();g=SendGuard(provider(),'TEST','actor',p2.base_body([]),ROOT,last_prompt(w));h={'x-p2-binding':g.token,'Authorization':'Bearer local-fixture'}
  with self.assertRaisesRegex(ValueError,'CLI_ROUTE_NOT_ALLOWED'):g.validate('/arbitrary',h,json.dumps(w).encode())
  w['tools']=[{'type':'function','name':'shell'}]
  with self.assertRaisesRegex(ValueError,'HOST_TOOLS_EXPOSED'):g.validate(UPSTREAM_PATH,h,json.dumps(w).encode())
 def test_05_budget_reserves_actor(self):
  p=provider();p.counts['TEST','derived']=108
  with self.assertRaises(p2.StopCampaign):p.admit('TEST','derived',p2.base_body([]))
  p.admit('TEST','actor',p2.base_body([]));p.counts['TEST','actor']=20
  with self.assertRaises(p2.StopCampaign):p.admit('TEST','actor',p2.base_body([]))
 def test_06_global_and_judge_budget(self):
  p=provider();p.state.value['requests']['attempts']=4096
  with self.assertRaises(p2.StopCampaign):p.admit('TEST','actor',p2.base_body([]))
  p=provider();p.counts['TEST','judge']=1
  with self.assertRaises(p2.StopCampaign):p.admit('TEST','judge',p2.base_body([]))
 def test_07_both_checks_and_noop_commit(self):self.effect(False)
 def test_08_deny_commit_enforced_after_both(self):self.effect(True)
 def effect(self,deny):
  directory=Path(tempfile.mkdtemp(prefix='effect-',dir=ROOT/'tmp'));work=directory/'workspace';work.mkdir()
  p=ScriptedProvider(deny);engine=EvidenceEngine(p,'TEST','Preserve a quoted report. Do not waive reviews.',[],directory/'evidence');a=EvidenceAdapter(engine,work)
  system='Host task rules.';self.assertEqual(a.initial(system,[{'role':'user','content':engine.task['user_request']}],engine.task['user_request'])[0],system)
  class D:
   def _record(self,*a,**k):pass
  raw='quoted payload';a.commit(D(),'write',{'path':'out.txt','content':raw},work/'out.txt','',raw)
  self.assertEqual([b.rsplit(':',1)[1] for b in p.boundaries],['dynamic_route','content_check','derived_check'])
  self.assertEqual((work/'out.txt').exists(),not deny)
  if not deny:self.assertEqual((work/'out.txt').read_text(),raw)
  checks=engine.results[-1]['checks_performed'];self.assertEqual([x['component'] for x in checks],['content','derived'])
 def test_09_local_forward_guard_counts_and_blocks_second(self):
  w=valid_wire();p=provider();directory=Path(tempfile.mkdtemp(prefix='guard-',dir=ROOT/'tmp'));g=SendGuard(p,'TEST','actor',p2.base_body([]),directory,last_prompt(w));made=[]
  payload=b'data: '+json.dumps({'type':'response.completed','response':{'status':'completed','model':p2.MODEL,'output':[]}}).encode()+b'\n\n'
  class Response(io.BytesIO):
   status=200
   def getheaders(self):return [('Content-Type','text/event-stream')]
  class Connection:
   def __init__(self,host,timeout):made.append(host)
   def request(self,method,path,body,headers):
    assert method=='POST' and path==UPSTREAM_PATH and headers['Authorization']=='Bearer local-fixture'
   def getresponse(self):return Response(payload)
   def close(self):pass
  server=ThreadingHTTPServer(('127.0.0.1',0),g.handler());threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   with patch('cli_transport.http.client.HTTPSConnection',Connection):
    for expected in [200,409]:
     c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5);c.request('POST',UPSTREAM_PATH,body=json.dumps(w),headers={'x-p2-binding':g.token,'Authorization':'Bearer local-fixture','Content-Type':'application/json'});res=c.getresponse();self.assertEqual(res.status,expected);res.read();c.close()
   self.assertEqual(made,[UPSTREAM_HOST]);self.assertEqual(p.state.value['requests']['attempts'],1);self.assertEqual(p.state.value['requests']['settled'],1);self.assertEqual(g.forwarded,1);self.assertEqual(g.rejected,1)
   self.assertNotIn('Bearer local-fixture',json.dumps(p.records))
  finally:server.shutdown();server.server_close()
 def test_10_tech_completion_is_not_a_native_safe(self):
  s=project_snapshot({'units':[{'unit_id':'TECH-01','eval_id':'TECH-01','phase':'TECH','status':'technical_complete','verdict':None}]})
  self.assertEqual(s['tech']['actor_terminal'],1);self.assertEqual(s['tech']['judged'],0);self.assertEqual(s['core']['judged'],0)

if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 summary={'passed':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'new_provider_requests':0,'fixtures_not_semantic_truth':True}
 (ROOT/'OFFLINE_TESTS.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
 sys.exit(0 if result.wasSuccessful() else 1)
