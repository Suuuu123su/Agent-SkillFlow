from pathlib import Path
p=Path(r'E:\Skill ＆ Harness\Agent\论文材料\P4_测量证据消融\p4-20260917-123623\code\views.py');s=p.read_text(encoding='utf-8-sig');s=s.replace("if family=='grant':\n", "if family=='grant':\n  if isinstance(result.get('declared_capability_rules'),dict):\n   m=result['declared_capability_rules'];atoms=sorted({r['grant_atom'] for r in m['rules'] if r.get('grant_atom')});m['initial']=[a for a in m['initial'] if a not in atoms];m['unknown_initial_atoms']=atoms\n")
p.write_text(s,encoding='utf-8')
p=p.parent/'predictor.py';s=p.read_text(encoding='utf-8-sig');start=s.index('  sets=[];witness=[]\n');end=s.index(' def grid(',start)
s=s[:start]+'''  unknown=model.get('unknown_initial_atoms',[]);completions=[]
  for bits in range(2**len(unknown)):
   initial=set(model['initial'])|{a for j,a in enumerate(unknown) if bits&(1<<j)};sets=[];witness=[]
   for on in [False,True]:
    start=frozenset(initial);queue=[start];paths={start:[]};effects=set();proof={}
    while queue:
     state=queue.pop(0)
     for r in model['rules']:
      if r.get('bridge') is not None and r['bridge']!=on:continue
      if not set(r['requires']+r.get('execution_requires',[]))<=state or set(r.get('forbids',[]))&state:continue
      nxt=frozenset((set(state)-set(r.get('remove',[])))|set(r['adds']))
      if nxt not in paths:paths[nxt]=paths[state]+[r['id']];queue.append(nxt)
      if r.get('effect') and not(r.get('manifest_declared') and r.get('grant_atom') in state):effects.add(r['effect']);proof[r['effect']]=paths[state]+[r['id']]
    sets.append(effects);witness.append(proof)
   added=sets[1]-sets[0];completions.append(dict(value=sum(universe[e] for e in added),off=sorted(sets[0]),on=sorted(sets[1]),added=sorted(added),witnesses=witness))
  return self.result(lower=min(v['value'] for v in completions),upper=max(v['value'] for v in completions),details={'allowed_initial_completions':len(completions),'completions':completions})
''' +s[end:];p.write_text(s,encoding='utf-8')
