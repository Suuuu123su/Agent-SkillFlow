"""Project channels before prediction; never edit prediction columns."""
import copy,re,hashlib
FAMILIES=['receipt','grant','provenance','counterfactual','task_success_evidence','lifecycle','scope_lifetime','decision_reason','failure','declared_capability_rules','irrelevant_metadata']
PROFILES={'V00':None,**{f'V{i:02}':f for i,f in enumerate(FAMILIES,1)},'V12':'rename'}
def renamed(value):
 if isinstance(value,str) and re.fullmatch(r'i_[0-9a-f]{24}',value):return 'i_'+hashlib.sha256(('P4-bijection|'+value).encode()).hexdigest()[:24]
 return value

def project(value,profile):
 family=PROFILES[profile]
 if family=='rename':
  if isinstance(value,dict):return {renamed(k):project(v,profile) for k,v in value.items()}
  if isinstance(value,list):return [project(v,profile) for v in value]
  return renamed(value)
 if isinstance(value,list):return [project(v,profile) for v in value]
 if not isinstance(value,dict):return value
 result={k:(None if k==family else project(v,profile)) for k,v in value.items()}
 if family=='grant':
  if isinstance(result.get('declared_capability_rules'),dict):
   m=result['declared_capability_rules'];atoms=sorted({r['grant_atom'] for r in m['rules'] if r.get('grant_atom')});m['initial']=[a for a in m['initial'] if a not in atoms];m['unknown_initial_atoms']=atoms
  if isinstance(result.get('scope_lifetime'),dict):result['scope_lifetime']['grant_limits']=None
  if isinstance(result.get('lifecycle'),dict):
   result['lifecycle']['grant_issue_positions']=None;result['lifecycle']['grant_boundary_sessions']=None
 if family=='lifecycle':
  if isinstance(result.get('task_success_evidence'),dict):
   for b in result['task_success_evidence']['artifacts']:b['session_id']=None
  if isinstance(result.get('scope_lifetime'),dict) and isinstance(result['scope_lifetime'].get('grant_limits'),dict):
   for lim in result['scope_lifetime']['grant_limits'].values():lim['session_id']=None
 if family=='provenance' and 'source_object' in result:result['source_object']=None
 if family=='failure' and result.get('layout')=='legacy' and isinstance(result.get('lifecycle'),dict):
  for s in result['lifecycle']['sessions']:s['observation_complete']=None
 return result
