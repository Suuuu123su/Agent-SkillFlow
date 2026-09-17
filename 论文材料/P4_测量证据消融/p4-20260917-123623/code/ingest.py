"""Trusted ingest only. Whitelist raw facts, never emit old verdicts or scenario policies."""
from common import *
from collections import defaultdict
import re

def opaque(v):return 'i_'+hashlib.sha256(('P4-fixed-projection-v1|'+str(v)).encode()).hexdigest()[:24]
def manifest_permissions(p):
 result=[];cur=None;inside=False
 for line in Path(p).read_text(encoding='utf-8-sig').splitlines():
  if line.strip()=='requested_permissions:':inside=True;continue
  if not inside or not line.strip() or line.lstrip().startswith('#'):continue
  if not line.startswith(' '):break
  t=line.strip()
  if t.startswith('- '):cur={};result.append(cur);t=t[2:]
  if t.startswith('{'):
   parts=t[1:-1].split(',')
  else:parts=[t]
  for part in parts:
   if ':' not in part or cur is None:continue
   k,v=part.split(':',1);v=v.strip().strip('\"\'');cur[k.strip()]=None if v in ['null','~'] else int(v) if v.isdigit() else v
 return result

def legacy(data,ref,unit=None,decisions=None,issues=None,status='completed',receipt_bytes=None):
 f=data['facts'] if 'facts' in data else data;unit=unit or f['run_id'];uid=opaque(unit);events=f['events'];ev={e['event_id']:e for e in events};order={e['event_id']:i for i,e in enumerate(events)};sid=[]
 for e in events:
  if e['event_type']=='session_start' and e['session_id'] not in sid:sid.append(e['session_id'])
 ops=[]
 for e in events:
  if e['event_type']!='tool_call_request' or not e.get('requested_effect'):continue
  eff=e['requested_effect'];rec=next((x for x in f['effects'] if x['request_event_id']==e['event_id']),None)
  ops.append(dict(id=opaque(e['event_id']),actor=opaque(e['actor_id']),action=eff['action'],source=eff['source'],sink=eff['sink'],requested_scope=eff['scope'],requested_lifetime=eff['lifetime'],sensitivity=eff['sensitivity'],position=order[e['event_id']],timestamp=e['timestamp'],effect_id=opaque(rec['effect_id']) if rec else None,call_id=opaque(e['call_id']),task_id=opaque(e['task_id'])))
 receipts=[dict(id=opaque(r['receipt_id']),op=opaque(r['request_event_id']),effect_id=opaque(r['effect_id']),result_event=opaque(r['result_event_id'])) for r in f['receipts']]
 arts=f['artifacts'];objs=[dict(id=opaque(a['artifact_id']),kind=a['artifact_type'],digest=a['content_hash'],length=a['content_length'],created_position=order.get(a['created_by_event_id'])) for a in arts]
 grants=[];limits={}
 for g in f['grants']:
  gid=opaque(g['grant_id']);grants.append(dict(id=gid,actor=opaque(g['grantee_id']),action=g['action']));limits[gid]={k:g.get(k) for k in ['source_pattern','sink_pattern','scope','lifetime','valid_from','expires_at']};limits[gid].update(task_id=opaque(g['task_id']),session_id=opaque(g['session_id']) if g.get('session_id') else None,call_id=opaque(g['call_id']) if g.get('call_id') else None)
 perms={};plimits={};definition=data.get('analysis_definition',{})
 for skill in definition.get('skills',[]):
  ps=manifest_permissions(ROOT/skill['manifest']);pids=[]
  for j,p in enumerate(ps):
   pid=opaque(skill['id']+':permission:'+str(j));pids.append(dict(id=pid,action=p['action']));plimits[pid]={k:p.get(k) for k in ['source','sink','scope','lifetime','sensitivity']}
  perms[opaque(skill['id'])]=pids
 issues=issues or [];decisions=decisions or []
 sessions=[dict(id=opaque(s),index=i,arrived=True,closed=any(e['event_type']=='session_end' and e['session_id']==s for e in events),observation_complete=not any(x.get('session_id')==s for x in issues) and all(x.get('behavior') not in ['schema_rejection','infrastructure_invalid'] for x in decisions if x.get('session_id')==s)) for i,s in enumerate(sid)]
 rev=[dict(target=opaque(r['target_id']),kind=r['target_kind'],position=order[r['event_id']],session=opaque(ev[r['event_id']]['session_id'])) for r in f['revocations']]
 claims=[]
 for b in data.get('claim_bindings',[]):
  for a in arts:
   if a['content_hash']==b['expected_content_hash']:claims.append(opaque(a['artifact_id']))
 for a in arts:
  if a.get('observed_label',{}).get('trust')=='untrusted' and a['artifact_type']=='claim':claims.append(opaque(a['artifact_id']))
 rawdec=f['decisions'];basis={opaque(d['request_event_id']):[opaque(a) for a in d['decision_basis_artifact_ids']] for d in rawdec}
 tc=data.get('task_contract',{});oblig=[];aliases=data.get('artifact_ids_by_alias',{})
 for x in tc.get('artifacts',[]):
  aid=aliases.get(x['alias']) or aliases.get('artifact:'+x['alias']);aid=aid if not isinstance(aid,list) else aid[-1] if aid else None
  oblig.append(dict(kind='artifact_digest',object_id=opaque(aid) if aid else None,required_digest=x['expected_sha256'],required_session=opaque(x['session_id'])))
 for x in tc.get('effects',[]):oblig.append(dict(kind='effect_contract',spec={'selector':{k:v for k,v in x['selector'].items() if k!='alias'},'required_session':opaque(x['session_id'])}))
 selectors=[{k:v for k,v in x.items() if k in ['action','source_pattern','sink_pattern']} for x in tc.get('risk_selectors',definition.get('effect_selectors',[]))]
 certificate=data.get('task_certificate_bindings') or data.get('proof',{}).get('task')
 bindings=None if not certificate else {'artifacts':[{'object_id':opaque(a['artifact_id']), 'actual_digest':a.get('actual_sha256'), 'session_id':opaque(a['session_id']) if a.get('session_id') else None} for a in certificate.get('artifacts',[]) if a.get('artifact_id')]}
 # Content hashes and published mechanical obligations are independent of a task verdict certificate.
 return dict(id=uid,layout='legacy',authorization_contract='manifest_and_scoped_grant',observation={'closed':status=='completed','ops':ops,'objects':objs,'task_obligations':oblig,'task_contract_present':bool(tc),'risk_selectors':selectors},receipt={'closed':True,'records':receipts},grant={'closed':True,'records':grants},manifest={'permissions':perms},scope_lifetime={'grant_limits':limits,'permission_limits':plimits},lifecycle={'sessions':sessions,'op_sessions':{opaque(e['event_id']):opaque(e['session_id']) for e in events if e['event_type']=='tool_call_request'},'object_sessions':{opaque(a['artifact_id']):opaque(ev[a['created_by_event_id']]['session_id']) for a in arts},'revocations':rev,'grant_issue_positions':{opaque(e['metadata']['grant_id']):order[e['event_id']] for e in events if e['event_type']=='auth_grant'},'grant_boundary_sessions':{opaque(g['grant_id']):opaque(g['session_id']) if g.get('session_id') else None for g in f['grants']}},provenance={'origins':{opaque(a['artifact_id']):[opaque(v) for v in a['observed_label']['origins']] for a in arts},'trust':{opaque(a['artifact_id']):a['observed_label']['trust'] for a in arts},'parents':{opaque(a['artifact_id']):list(dict.fromkeys([opaque(v) for v in a['observed_label']['parent_artifact_ids']]+[opaque(v) for v in ev[a['created_by_event_id']]['input_artifact_ids']])) for a in arts},'request_basis':basis,'claim_objects':list(set(claims)),'object_creators':{opaque(a['artifact_id']):opaque(ev[a['created_by_event_id']]['actor_id']) for a in arts}},decision_reason={opaque(d['request_event_id']):d.get('baseline_reason') for d in rawdec},failure={'steps':[dict(behavior=x.get('behavior'),schema_valid=x.get('schema_valid')) for x in decisions],'issues':[x.get('reason') for x in issues]},task_success_evidence=bindings,counterfactual=[],irrelevant_metadata={'display_title':'Saved observation'})

def reference(state,unit,ref,base):
 uid=opaque(unit);events=state['events'];ev={x['id']:x for x in events};ops=[];receipts=[];artifacts=state['artifacts'];own=[x for x in events if x['unit']==unit]
 for e in events:
  if e['kind']!='request':continue
  ops.append(dict(id=opaque(e['id']),actor=opaque(e['actor']),action=e['action'],source='memory:/saved' if e['action']=='network.send' else 'local:/synthetic',sink='mock://external' if e['action']=='network.send' else 'local:/synthetic',requested_scope='action-only',requested_lifetime='task',sensitivity=1,position=e['seq'],timestamp=None,effect_id=opaque(next((x['effect_id'] for x in events if x['kind']=='effect' and x['request_id']==e['id']),None)),call_id=opaque(e['id']),task_id=opaque('shared-task'),args=e['args'],belongs_to_current=e['unit']==unit))
 for e in events:
  if e['kind']!='effect':continue
  r=e['receipt'];receipts.append(dict(id=opaque(r['receipt_id']),op=opaque(e['request_id']),effect_id=opaque(e['effect_id']),result_event=opaque(e['id'])))
 objs=[dict(id=opaque(k),kind=a['kind'],digest=a['sha256'],content=a['value'],created_position=next((x['seq'] for x in events if x['kind']=='effect' and x['receipt'].get('artifact_id')==k),None)) for k,a in artifacts.items()]
 decl=[x for x in events if x['kind']=='decision'];claims=[opaque(k) for k,a in artifacts.items() if a['kind']=='claim' and a['value'].get('approval_claim')]
 grants=[dict(id=opaque(g['id']),actor=opaque(g['actor']),action=g['action']) for g in state['grants']]
 after=[]
 for e in own:
  if e['kind']=='effect' and e['action']=='task.write':
   f=base/e['receipt']['file'];raw=f.read_bytes();assert hashlib.sha256(raw).hexdigest()==e['receipt']['sha256'];after.append(dict(op=opaque(e['request_id']),value=json.loads(raw),digest=e['receipt']['sha256']))
 return dict(id=uid,layout='reference',authorization_contract='action_registry_v1',observation={'closed':all(v['complete'] for v in state['sessions'].values()),'ops':ops,'objects':objs,'task_obligations':[dict(kind='task_record',ticket_id=state['scenario']['facts']['ticket_id'])],'task_contract_present':state['scenario']['module']=='RIR','risk_selectors':[{'action':'network.send','source_pattern':'memory:/saved','sink_pattern':'mock://external'}],'postimages':after,'current_unit_ops':[x['id'] for x in ops if x['belongs_to_current']]},receipt={'closed':True,'records':receipts},grant={'closed':True,'records':grants},manifest={'action_registry':True},scope_lifetime={'action_only_no_extra_constraints':True},lifecycle={'sessions':[dict(id=opaque('session'+str(k)),index=int(k),arrived=v['started'],closed=v['complete'],observation_complete=v['complete']) for k,v in state['sessions'].items()],'op_sessions':{opaque(e['id']):opaque('session'+str(e['session'])) for e in events if e['kind']=='request'},'object_sessions':{opaque(k):opaque('session'+str(a['session'])) for k,a in artifacts.items()},'revocations':[dict(target=opaque(e['target']),kind='principal',position=e['seq'],session=opaque('session'+str(e['session']))) for e in own if e['kind']=='revoke'],'grant_issue_positions':{g['id']:0 for g in grants},'grant_boundary_sessions':{}},provenance={'origins':{},'trust':{opaque(k):'untrusted' for k in artifacts},'parents':{opaque(k):[opaque(p) for p in a['parents']] for k,a in artifacts.items()},'request_basis':{opaque(d['request_id']):[opaque(v) for v in d['basis']] for d in decl},'claim_objects':claims,'object_creators':{opaque(k):opaque(a['producer']) for k,a in artifacts.items()}},decision_reason={opaque(d['request_id']):d.get('reason') for d in decl},failure={'steps':[],'issues':[]},task_success_evidence=None,counterfactual=[],irrelevant_metadata={'display_title':'Saved observation'})
