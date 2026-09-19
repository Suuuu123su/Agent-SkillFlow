"""Read-only arithmetic and SHA verification; never executes a scenario or policy."""
import argparse
import json
from pathlib import Path
from experiments.evidence_contract_validation.common import load_frozen, read_json, sha
from . import audit
from .reanalysis import check_map


def verify(old, out, snapshot):
    plan = load_frozen(out/'CLOSEOUT_PLAN.json')
    root = Path(__file__).resolve().parents[2]
    check_map(old,plan['original_inputs'])
    check_map(root,plan['source_hashes'])
    assert sha((old/'FINAL_PLAN.json').read_bytes()) == plan['parent_final_plan_sha256']
    audit.REPO=snapshot
    parent=audit.verify(old,False)
    corrected={}
    for split in ('development','heldout'):
        q={q['query_id']:q for q in read_json(old/f'{split}_QUERIES.json')}
        corrected[split]=audit.audit_trajectories(out,split,plan,q,read_json(old/'oracle'/f'{split}.json'))
    stored=read_json(out/'CLOSEOUT_RESULTS.json')
    assert corrected == stored['independent_audit']
    return {'status':'PASSED','parent_executions':parent['actual_attempts_in_ledger'],
            'parent_prediction_cost_pairs':sum(v['rows'] for v in parent['replays'].values()),
            'corrected_prediction_cost_pairs':sum(v['rows'] for v in corrected.values()),
            'new_executions':0,'new_predictions':0,'model_calls':0,'dual_os_execution':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--old',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--source-snapshot',required=True,type=Path)
    a=p.parse_args()
    print(json.dumps(verify(a.old.resolve(),a.out.resolve(),a.source_snapshot.resolve()),indent=2))
