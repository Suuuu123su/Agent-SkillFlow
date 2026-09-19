"""Three pre-execution methods receive identical JSON; no result paths accepted."""
import json
import sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[2]/'src')]


def b0(d):
    # Full public native gating supplied to the elementary baseline as well.
    for a in d['actions']:
        executed=a['tool'] in d['native']['allowed_tools'] and (not d['native']['workspace_only'] or a['resource'].startswith('workspace/'))
        authorized=any(g['kind']=='grant' and g['tool']==a['tool'] and g['resource']==a['resource']
                       and g['session']==d['session'] and g['issued']<=d['time']<g['expires'] for g in d['prefix'])
        if executed and not authorized:return True
    return False


def b1(d):
    # Short stateful relation checker; complete legal history, exact resource/session.
    live={}
    for event in d['prefix']:
        key=(event['tool'],event['resource'],event['session'])
        if event['kind']=='grant':live[key]=event
        elif event['kind']=='revoke':live.pop(key,None)
    for a in d['actions']:
        if a['tool'] not in d['native']['allowed_tools']:continue
        if d['native']['workspace_only'] and not a['resource'].startswith('workspace/'):continue
        g=live.get((a['tool'],a['resource'],d['session']))
        if g is None or not g['issued']<=d['time']<g['expires']:return True
    return False


def skillflow(d):
    from skillflow.graph.security import SecurityGraph
    from skillflow.graph.models import GraphBuildData,GrantGraphNode,EffectGraphNode,SecurityEdge,node_ref
    from skillflow.graph.enums import SecurityRelation
    from skillflow.models.enums import CapabilityAction
    nodes=[];edges=[];effects=[]
    for i,a in enumerate(d['actions']):
        # Hypothetical requested effects, never asserted to have occurred.
        e=EffectGraphNode(node_id=f'request-{i}',run_id='pre-execution-hypothesis',action=CapabilityAction.FILE_WRITE,executed=False)
        nodes.append(e);effects.append((e,a))
        for j,g in enumerate(d['prefix']):
            if g['kind']!='grant':continue
            revoked=any(r['kind']=='revoke' and (r['tool'],r['resource'],r['session'])==(g['tool'],g['resource'],g['session']) for r in d['prefix'][j+1:])
            if not revoked and g['tool']==a['tool'] and g['resource']==a['resource'] and g['session']==d['session'] and g['issued']<=d['time']<g['expires']:
                grant=GrantGraphNode(node_id=f'grant-{i}-{j}',run_id='pre-execution-hypothesis');nodes.append(grant)
                edges.append(SecurityEdge(source=node_ref(grant),target=node_ref(e),relation=SecurityRelation.AUTHORIZE,
                    session_ids=(d['session'],),evidence_event_ids=(f'prefix-{j}',)))
    graph=SecurityGraph(GraphBuildData('pre-execution-hypothesis',tuple(nodes),(),tuple(edges),()))
    violations=[]
    for e,a in effects:
        reaches=a['tool'] in d['native']['allowed_tools'] and (not d['native']['workspace_only'] or a['resource'].startswith('workspace/'))
        if reaches and not graph.find_authorization_path(e.node_id):violations.append(e.node_id)
    return bool(violations),violations


def predict(d):
    # No family, split, condition, result, path-to-result, receipt, or oracle field.
    if set(d)!={'native','session','time','prefix','actions'}:raise ValueError('Unexpected predictor input')
    sf,relations=skillflow(d)
    return {'B0':b0(d),'B1':b1(d),'SkillFlow':sf,'violated_relations':relations,
            'recommended':'enable_native_workspace_only' if sf else None,
            'unrelated':'logging_level_debug','graph_status':'hypothetical requested effects, executed=false'}


if __name__=='__main__':
    for line in sys.stdin:
        print(json.dumps(predict(json.loads(line)),sort_keys=True),flush=True)
