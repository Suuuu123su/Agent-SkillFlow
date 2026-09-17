"""Finite declarative transition model. No runtime observations are inputs."""
from collections import deque

def declared_reach(model,bridge):
 if not model.get('closed') or model.get('unknown_semantics'):
  return {'status':'UNKNOWN','lower':[], 'upper':sorted(model['universe']),'witnesses':{},'reason':'undeclared parameter/policy semantics'}
 atoms=set(model['atoms']);initial=frozenset(model['initial']);assert initial<=atoms
 states={initial:[]};pending=deque([initial]);witness={}
 while pending:
  state=pending.popleft();path=states[state]
  for rule in model['rules']:
   if rule.get('bridge') is not None and rule['bridge']!=bridge:continue
   if not set(rule['requires'])<=state or set(rule.get('forbids',[]))&state:continue
   # Native execution and authorization are distinct AND-constrained predicates.
   if not set(rule.get('execution_requires',[]))<=state:continue
   nxt=frozenset((set(state)-set(rule.get('remove',[])))|set(rule['adds']));assert nxt<=atoms
   if rule.get('effect'):
    has_grant=rule.get('grant_atom') in state;manifest=rule.get('manifest_declared',False)
    if not(has_grant and manifest):witness.setdefault(rule['effect'],path+[rule['id']])
   if nxt not in states:states[nxt]=path+[rule['id']];pending.append(nxt)
 return {'status':'EXACT_DECLARED_FINITE_MODEL','lower':sorted(witness),'upper':sorted(witness),'witnesses':witness,'visited_states':len(states)}

def potential(model):
 a,b=declared_reach(model,False),declared_reach(model,True);w=model['universe'];assert all(v>=0 for v in w.values())
 lo=set(b['lower'])-set(a['upper']);hi=set(b['upper'])-set(a['lower'])
 return {'h0':a,'h1':b,'difference_lower':sorted(lo),'difference_upper':sorted(hi),'lower':sum(w[x] for x in lo),'upper':sum(w[x] for x in hi),'exact':a['status']==b['status']=='EXACT_DECLARED_FINITE_MODEL'}

def independent_bit_enumeration(model,bridge):
 """Separate exhaustive finite-state graph construction, no call to closure solver."""
 if not model.get('closed') or model.get('unknown_semantics'):return None
 names=model['atoms'];idx={s:1<<i for i,s in enumerate(names)}
 def mask(seq):return sum(idx[x] for x in seq)
 edges={};effects={}
 for state in range(1<<len(names)):
  edges[state]=set();effects[state]=set()
  for r in model['rules']:
   need=mask(r['requires']+r.get('execution_requires',[]));ban=mask(r.get('forbids',[]))
   if (r.get('bridge') is not None and r['bridge']!=bridge) or state&need!=need or state&ban:continue
   edges[state].add((state&~mask(r.get('remove',[])))|mask(r['adds']))
   g=idx.get(r.get('grant_atom'),0)
   if r.get('effect') and not(r.get('manifest_declared',False) and state&g):effects[state].add(r['effect'])
 reached={mask(model['initial'])}
 while True:
  expanded=reached|set().union(*(edges[i] for i in reached))
  if expanded==reached:break
  reached=expanded
 return sorted(set().union(*(effects[i] for i in reached)))
