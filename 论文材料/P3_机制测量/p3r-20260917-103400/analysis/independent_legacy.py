"""Standard-library independent Grant/graph/bootstrap checker. No skillflow imports."""
from common import *
from collections import defaultdict,Counter
import math,random
LIFE={'call':{'call'},'task':{'call','task'},'session':{'call','session'},'persistent':{'call','task','session','persistent'}}
def simple_manifest(p):
 result=[];cur=None;inside=False
 for line in p.read_text(encoding='utf-8').splitlines():
  if line.strip()=='requested_permissions:':inside=True;continue
  if not inside or not line.strip() or line.lstrip().startswith('#'):continue
  if not line.startswith(' '):break
  s=line.strip()
  if s.startswith('- '):cur={};result.append(cur);s=s[2:]
  if s.startswith('{') and s.endswith('}'):
   for part in s[1:-1].split(','):
    k,v=part.split(':',1);v=v.strip();cur[k.strip()]=int(v) if v.isdigit() else v
   continue
  if ':' in s and cur is not None:
   k,v=s.split(':',1);v=v.strip().strip('"\'');cur[k]=None if v in ['null','~'] else int(v) if v.isdigit() else v
 return result

def auth_check(data):
 f=data['facts'];events={e['event_id']:e for e in f['events']};order={e['event_id']:i for i,e in enumerate(f['events'])};perms={s['id']:simple_manifest(ROOT/s['manifest']) for s in data['analysis_definition']['skills']};out=[]
 for o in data['oracle']:
  if o.get('record_type')!='effect':continue
  er=next(e for e in f['effects'] if e['effect_id']==o['effect_id']);req=events[er['request_event_id']];e=er['effect'];revoked={rv['target_id'] for rv in f['revocations'] if rv['target_kind']=='grant' and order[rv['event_id']]<order[req['event_id']]}
  def cover(g,grant):
   return g['action']==e['action'] and g.get('source_pattern' if grant else 'source')==e.get('source') and g['sink_pattern' if grant else 'sink']==e['sink'] and g['scope']==e['scope'] and e['lifetime'] in LIFE[g['lifetime']] and (grant or g['sensitivity']>=e['sensitivity'])
  matched=[]
  for g in f['grants']:
   issue=next((z for z in f['events'] if z['event_type']=='auth_grant' and z['metadata'].get('grant_id')==g['grant_id']),None)
   boundary={'call':g.get('call_id')==req['call_id'],'task':g['task_id']==req['task_id'],'session':g.get('session_id')==req['session_id'],'persistent':True}[g['lifetime']]
   if issue is not None and order[issue['event_id']]<=order[req['event_id']] and g['grant_id'] not in revoked and g['grantee_id']==req['actor_id'] and cover(g,True) and boundary and g['valid_from']<=req['timestamp'] and (g['expires_at'] is None or req['timestamp']<g['expires_at']):matched.append(g['grant_id'])
  declared=any(cover(p,False) for p in perms[req['actor_id']]);value=bool(matched) and declared
  receipt=next((r for r in f['receipts'] if r.get('receipt_id')==er['tool_receipt_id']),None)
  out.append(dict(run_id=f['run_id'],effect_id=er['effect_id'],value=value,oracle=o['gt_auth'],match=value==o['gt_auth'],matched_grants=matched,grant_set_match=set(matched)==set(o['matched_grant_ids']),manifest_declared=declared,manifest_match=declared==o['manifest_declared'],receipt_present=receipt is not None,manifest_provenance='current named manifest; separately hashed; historical exact manifest byte binding not independently recovered'))
 return out

def graph_check(data,expected):
 f=data['facts'];ev={e['event_id']:e for e in f['events']};arts={a['artifact_id']:a for a in f['artifacts']};parents=defaultdict(list);forward=defaultdict(list);nodes=set()
 def edge(s,t,weight,sid):
  if (s,weight,sid) not in parents[t]:parents[t].append((s,weight,sid));forward[s].append((t,weight,sid));nodes.update([s,t])
 active_in={'skill_invoke','skill_return','context_add','context_read','context_summarize','memory_write','memory_read','memory_delete','file_write','tool_call_request','tool_call_allow','tool_call_deny','tool_call_result','artifact_derive','sensitive_effect'}
 active_out={'skill_return','context_add','context_read','context_summarize','memory_write','memory_read','file_read','file_write','tool_call_request','tool_call_result','artifact_register','artifact_derive'}
 for e in f['events']:
  typ=e['event_type'];eid=('event',e['event_id']);actor=('principal',e['actor_id']);sid=e['session_id'];b=1 if typ.startswith(('context_','memory_')) or typ in ['tool_call_allow','tool_call_deny','sensitive_effect'] else 0
  for aid in e['input_artifact_ids'] if typ in active_in else []:edge(('artifact',aid),eid,b,sid)
  for aid in e['output_artifact_ids'] if typ in active_out else []:
   a=arts[aid];w=(b if not e['input_artifact_ids'] else 0)+int(a['artifact_type']=='context' and not typ.startswith('context_'))+int(a['artifact_type']=='memory' and b==0);edge(eid,('artifact',aid),w,sid)
  if typ=='skill_invoke':edge(eid,actor,1,sid)
  if typ=='skill_return':edge(actor,eid,1,sid)
  if typ=='tool_call_result':edge(actor,eid,1,sid)
  if typ=='tool_call_request':
   if not e['input_artifact_ids'] or not any(e['actor_id'] in arts[a]['observed_label']['origins'] for a in e['input_artifact_ids']):edge(actor,eid,1,sid)
   tool=e['metadata']['tool'];edge(eid,('principal',tool if tool.startswith('tool:') else 'tool:'+tool),1,sid)
 # enumerate paths from all ancestor nodes in sorted order, same published path truncation contract, different implementation
 output=[]
 for aid in arts:
  target=('artifact',aid);anc=set();stack=[s for s,_,_ in parents[target]]
  while stack:
   u=stack.pop()
   if u in anc or u==target:continue
   anc.add(u);stack.extend(x[0] for x in parents[u])
  count=0;maximum=0;limit=False
  def walk(node,visited,depth,weight,previous):
   nonlocal count,maximum,limit
   if count>=512:limit=True;return
   if node==target and depth:
    count+=1;maximum=max(maximum,weight);return
   if depth>=64:return
   for nxt,w,sid in sorted(forward[node]):
    if nxt not in visited:walk(nxt,visited|{nxt},depth+1,weight+w+int(previous is not None and previous!=sid),sid)
  for s in sorted(anc):
   if count>=512:limit=True;break
   walk(s,{s},0,0,None)
  output.append(dict(run_id=f['run_id'],artifact_id=aid,depth=maximum,expected_depth=expected.get((f['run_id'],aid)),match=maximum==expected.get((f['run_id'],aid)),paths=count,truncated=limit))
 # Reconstruct oracle origin sets by typed parent propagation; root assets from scenario resource declarations.
 oracle={x['artifact_id']:x for x in data['oracle'] if x.get('record_type')=='artifact'};origin={};vis=set();issues=[]
 def calc(aid):
  if aid in origin:return origin[aid]
  if aid in vis:raise ValueError('ORACLE_PARENT_CYCLE')
  vis.add(aid);o=oracle[aid];assert o['run_id']==f['run_id'];ps=[x['parent_id'] for x in o['parents']];typ=o['value_type']; inherited=set().union(*(calc(x) for x in ps)) if ps else set()
  if typ=='asset':
   asset=next(a for a in data['analysis_definition']['assets'] if 'asset:'+a['id']==aid);uri=asset['uri'];value={uri.replace('fixture://','workspace:/')}
  else:
   e=ev[arts[aid]['created_by_event_id']];actor=e['actor_id']
   if actor.startswith('tool:'):
    request=next((v for v in f['events'] if v['event_type']=='tool_call_request' and v['call_id']==e['call_id']),None);actor=request['actor_id'] if request else actor
   if typ=='tool_return':value={actor}
   elif typ=='skill_output':value=inherited|{actor}
   elif typ=='tool_arg':value=inherited if ps else {actor}
   else:value=inherited
  vis.remove(aid);origin[aid]=value
  if value!=set(o['gt_data']):issues.append(dict(artifact_id=aid,type=typ,actual=sorted(value),expected=o['gt_data']))
  return value
 for aid in oracle:calc(aid)
 return output,issues,dict(artifact_count=len(arts),oracle_count=len(oracle),duplicate_artifacts=len(arts)!=len(f['artifacts']),cross_run=any(e['run_id']!=f['run_id'] for e in f['events']),parent_cycle=False)

def interval_check(vectors):
 out=[];indices={}
 for phase,vector in vectors.items():
  if phase not in ['f','g','h']:continue
  for metric,v in vector.items():
   terms=v.get('cluster_terms',[]);signs=v.get('contrast_signs',{}) or {'value':1};group=defaultdict(lambda:defaultdict(lambda:[0.,0.]))
   for t in terms:group[t['cluster']][t['term']][0]+=t['numerator'];group[t['cluster']][t['term']][1]+=t['denominator']
   names=[c for c in sorted(group) if all(t in group[c] and group[c][t][1]>0 for t in signs)]
   for old in v.get('intervals',[]):
    if old['status']!='measured':continue
    if old['method']=='cluster_bootstrap':
     n=len(names)
     if n not in indices:
      rng=random.Random(17017);indices[n]=[rng.choices(range(n),k=n) for _ in range(10000)]
     def estimate(ix):return sum(s*sum(group[names[i]][t][0] for i in ix)/sum(group[names[i]][t][1] for i in ix) for t,s in signs.items())
     values=sorted(estimate(ix) for ix in indices[n]);point=estimate(range(n))
     def quant(p):
      z=p*9999;i=math.floor(z);return values[i]+(z-i)*(values[math.ceil(z)]-values[i])
     lower,upper=quant(.025),quant(.975)
    elif old['method']=='wilson_chain_descriptive':
     x,n=v['numerator'],v['denominator'];point=x/n;z=1.959963984540054;den=1+z*z/n;mid=(point+z*z/2/n)/den;rad=z*math.sqrt(point*(1-point)/n+z*z/4/n/n)/den;lower=max(0,mid-rad);upper=min(1,mid+rad)
    else:continue
    errors=[abs(actual-old[k]) for actual,k in [(point,'point'),(lower,'lower'),(upper,'upper')]];out.append(dict(phase=phase,metric=metric,method=old['method'],point=point,lower=lower,upper=upper,max_error=max(errors),match=max(errors)<1e-12,clusters=len(names)))
 return out
if __name__=='__main__':
 offline_guard();expected={(x['run_id'],x['artifact_id']):x['depth'] for x in rows(OLD/'facts/PROVENANCE.jsonl')};auth=[];graphs=[];origins=[];integrity=[];manifest_hashes={}
 for phase in ['f','g','h']:
  for c,ref in table(phase,'core-trials'):
   a=c['data'];auth.extend(dict(phase=phase,**x) for x in auth_check(a));depth,issues,integ=graph_check(a,expected);graphs.extend(dict(phase=phase,**x) for x in depth);origins.extend(dict(phase=phase,run_id=c['run_id'],**x) for x in issues);integrity.append(dict(phase=phase,run_id=c['run_id'],**integ))
   for s in a['analysis_definition']['skills']:manifest_hashes[s['manifest']]=sha(ROOT/s['manifest'])
  print('Independent facts',phase,flush=True)
 csvout('audit/INDEPENDENT_AUTHORIZATION.csv',auth);csvout('audit/INDEPENDENT_GRAPH_DEPTH.csv',graphs);jl('audit/INDEPENDENT_ORIGIN_DIFFERENCES.jsonl',origins);dump('audit/GRAPH_INTEGRITY.json',integrity);dump('audit/MANIFEST_SOURCE_HASHES.json',manifest_hashes)
 stats=interval_check(read(OLD/'facts/FRESH_VECTORS.json'));csvout('audit/INDEPENDENT_INTERVALS.csv',stats)
 result=dict(cores=len(integrity),auth_checks=len(auth),auth_mismatch=sum(not x['match'] for x in auth),grant_mismatch=sum(not x['grant_set_match'] for x in auth),manifest_mismatch=sum(not x['manifest_match'] for x in auth),graph_checks=len(graphs),graph_mismatch=sum(not x['match'] for x in graphs),graph_truncated=sum(x['truncated'] for x in graphs),origin_mismatch=len(origins),interval_checks=len(stats),interval_mismatch=sum(not x['match'] for x in stats));dump('audit/INDEPENDENT_SUMMARY.json',result);print(result)

