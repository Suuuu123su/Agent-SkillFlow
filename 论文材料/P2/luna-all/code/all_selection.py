"""Only override review selection at the same applicable v3 boundaries."""
from evidence_method.selector import select,bind,action
from evidence_method.execution import execute_plan
from evidence_method.config import DefenseConfig

def execute_all(services,context,config,*,reviewer):
 decision=select(context,config)
 # Same v3 exemptions: host system and metadata/native error have known use support.
 answers=context.export()['answers']
 support=answers['use_support']
 exempt=support.get('status')=='KNOWN_SUPPORTED' and support.get('value') is True
 if not exempt and context.binding['use']!='data':
  decision['requested_reviews']=[action(c,scope=context.binding['scope']) for c in ('content','derived')]
  decision['proposed_interventions']=[]
  decision['selection_policy']='all_same_library'
  decision['reason_codes']=['FIXED_BOTH_SAME_APPLICABLE_V3_BOUNDARY']
  decision['unresolved_requirements']=['CURRENT_USE_OR_OBJECT_KIND_UNRESOLVED']
 frozen=bind(context,decision,services)
 return execute_plan(services,context,frozen,reviewer=reviewer)

def install():
 import evidence_engine
 evidence_engine.execute_content=execute_all
