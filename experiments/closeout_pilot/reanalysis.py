"""One append-only reanalysis of already disclosed data. No collection API."""
from collections import Counter
from pathlib import Path
import argparse
import csv
import gzip
import json
import platform
import sys

from experiments.evidence_contract_validation.common import (
    ROOT, append_json, frozen_json, load_frozen, now, read_json, sha, write_csv, write_json)
from experiments.evidence_contract_validation import reporting as stats
from . import audit
from .evaluation import choose_static, replay
from .paths import confined


def file_map(root):
    return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob('*')
            if p.is_file() and not any(x in p.parts for x in ('policy_ipc','validation_tmp','.mplconfig'))}


def check_map(root, mapping):
    for relative, digest in mapping.items():
        if sha(confined(root, relative).read_bytes()) != digest:
            raise ValueError('Sealed file changed: '+relative)


def summarize(old, out, plan):
    family_rows, curves, audits, changes = [], [], {}, Counter()
    with gzip.open(out/'ROW_CHANGES.csv.gz','wt',encoding='utf-8',newline='') as change_file:
        writer = csv.DictWriter(change_file, fieldnames=['split','row_id','query_id','policy','budget',
                                 'old_status','new_status','old_value','new_value','old_bytes','new_bytes',
                                 'old_missing','new_missing','old_order','new_order'])
        writer.writeheader()
        for split in ('development','heldout'):
            oracle = read_json(old/'oracle'/f'{split}.json')
            full = read_json(old/'evaluation_only'/f'{split}_FULL.json')
            queries = read_json(old/f'{split}_QUERIES.json')
            # Independent arithmetic audit of every cost/prediction pair.
            audits[split] = audit.audit_trajectories(out,split,plan,{q['query_id']:q for q in queries},oracle)
            measured = []
            with gzip.open(out/f'{split}_PREDICTIONS.jsonl.gz','rt',encoding='utf-8') as current, \
                 gzip.open(old/f'{split}_PREDICTIONS.jsonl.gz','rt',encoding='utf-8') as parent:
                for new_line, old_line in zip(current,parent,strict=True):
                    a,b = json.loads(old_line),json.loads(new_line)
                    if a['row_id'] != b['row_id']:
                        raise ValueError('Row pairing mismatch')
                    key_fields = ('query_id','policy','budget','condition','seed')
                    if any(a[k] != b[k] for k in key_fields):
                        raise ValueError('Repeated measurement matrix changed')
                    m = stats._measure(b,oracle[b['query_id']],full[b['query_id']],b['metric'])
                    m.update({k:b[k] for k in ('split','query_id','unit','family_id','metric','mechanism','condition','budget')})
                    m['policy_family'] = stats._policy(b['policy'])
                    measured.append(m)
                    if any(a[k] != b[k] for k in ('status','value','charged_total_bytes','missing_channels','acquired_order')):
                        changes[split+':'+b['policy']] += 1
                        writer.writerow(dict(split=split,row_id=b['row_id'],query_id=b['query_id'],policy=b['policy'],budget=b['budget'],
                            old_status=a['status'],new_status=b['status'],old_value=a['value'],new_value=b['value'],
                            old_bytes=a['charged_total_bytes'],new_bytes=b['charged_total_bytes'],
                            old_missing=json.dumps(a['missing_channels']),new_missing=json.dumps(b['missing_channels']),
                            old_order=json.dumps(a['acquired_order']),new_order=json.dumps(b['acquired_order'])))
            f = stats._family_tables(stats._collapse_repeats(measured))
            family_rows.extend(f)
            curves.extend(stats._aggregate(f))
    write_csv(out/'PER_FAMILY.csv',family_rows)
    write_csv(out/'AGGREGATE_CURVES.csv',curves)
    with (old/'AGGREGATE_CURVES.csv').open(encoding='utf-8-sig') as stream:
        old_curves = {tuple(row[k] for k in ('split','mechanism','metric','policy','budget')):row for row in csv.DictReader(stream)}
    comparisons = []
    for row in curves:
        key = tuple(str(row[k]) for k in ('split','mechanism','metric','policy','budget'))
        old_row = old_curves[key]
        for metric in stats.RATE_DEFINITIONS:
            field = 'family_equal_'+metric
            before = float(old_row[field]) if old_row[field] else None
            after = row[field]
            comparisons.append(dict(zip(('split','mechanism','metric','policy','budget'),key),
                                    measure=metric,old=before,corrected=after,
                                    difference=after-before if after is not None and before is not None else None))
    write_csv(out/'OLD_VS_CORRECTED.csv',comparisons)
    # Compare report and independent audit, including all 80 ALL curves.
    compared = 0
    for split,value in audits.items():
        for expected in value['family_equal_curves']:
            row = next(r for r in curves if r['split']==split and r['mechanism']==r['metric']=='ALL'
                       and r['policy']==expected['policy'] and r['budget']==expected['budget'])
            assert abs(row['family_equal_correct_point_coverage']-expected['correct_coverage']) < 1e-12
            assert abs(row['family_equal_wrong_point_rate']-expected['wrong_point_rate']) < 1e-12
            compared += 1
    result = {'status':'CLOSED_EXPLORATORY_REANALYSIS','new_business_executions':0,'model_calls':0,
              'independent_audit':audits,'curves_independently_compared':compared,'changed_rows':dict(changes),
              'static_vs_global':stats._compare(curves,family_rows,plan['budgets'],'metric_static','global_fixed'),
              'dynamic_vs_static':stats._compare(curves,family_rows,plan['budgets'],'dependency_guided','metric_static'),
              'highest_budget':[r for r in curves if r['split']=='heldout' and r['mechanism']==r['metric']=='ALL' and r['budget']==max(plan['budgets'])],
              'scope':'Already disclosed heldout reanalysis; finite persistent-effect contract and padded-byte proxy only; not a new blind test'}
    write_json(out/'CLOSEOUT_RESULTS.json',result,exclusive=True)
    return result


def run(old, out, snapshot):
    out.mkdir(parents=True,exist_ok=True)
    if (out/'CLOSEOUT_REGISTRATION.json').exists():
        raise FileExistsError('Single-use closeout; do not overwrite a previous attempt')
    append_json(out/'COMMANDS.jsonl',{'at':now(),'argv':sys.argv,'python':sys.version,'platform':platform.platform()})
    audit.REPO = snapshot
    old_audit = audit.verify(old,False)
    write_json(out/'PARENT_AUDIT.json',old_audit,exclusive=True)
    parent = load_frozen(old/'FINAL_PLAN.json')
    old_files = file_map(old)
    new_files = {p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in Path(__file__).parent.glob('*.py')}
    new_files.update(parent['code_hashes'])
    candidates = read_json(old/'STATIC_CANDIDATES_REVISION1.json')
    reg = {'at':now(),'parent_final_plan_sha256':sha((old/'FINAL_PLAN.json').read_bytes()),
           'parent_commit':'317ff3199f087abd375ebb4560d72b118cb58f46','parent_run':old.relative_to(ROOT).as_posix(),
           'original_inputs':old_files,'source_hashes':new_files,
           'reasons':['portable confined relative reader','ACK hidden session requires lifecycle','same family-equal trapezoid AUC for selection and reporting'],
           'candidate_sha256':sha((old/'STATIC_CANDIDATES_REVISION1.json').read_bytes()),
           'candidate_orders':[{k:r[k] for k in ('metric','candidate_index','order')} for r in candidates],
           'budgets':parent['budgets'],'quotes':parent['quotes'],'splits':'unchanged 24/24; 6/6 families',
           'selection_objective':'(-raw wrong count, family-equal seed-averaged normalized trapezoid coverage AUC, -weighted bytes, -original candidate index)',
           'new_business_execution_cap':0,'model_call_cap':0,
           'interpretation':'Already disclosed heldout; not independent blind confirmation'}
    frozen_json(out/'CLOSEOUT_REGISTRATION.json',reg)
    selected, table = choose_static(read_json(old/'licensed_source/development.json'),
        read_json(old/'development_QUERIES.json'),parent['quotes'],parent['budgets'],
        read_json(old/'oracle/development.json'),out/'policy_ipc'/'selection',candidates)
    write_json(out/'STATIC_CANDIDATES.json',table,exclusive=True)
    plan = reg | {'frozen_at':now(),'selected_static':selected,'run_dynamic':True,
                  'policy_seeds':parent['policy_seeds'],'missing_seeds':parent['missing_seeds']}
    frozen_json(out/'CLOSEOUT_PLAN.json',plan)
    for split in ('development','heldout'):
        check_map(old,old_files)
        check_map(ROOT,new_files)
        append_json(out/'ACCESS_LOG.jsonl',{'at':now(),'action':'replay_'+split,'oracle_joined_by_replay':False})
        replay(out,split,read_json(old/'licensed_source'/f'{split}.json'),read_json(old/f'{split}_QUERIES.json'),plan)
    append_json(out/'ACCESS_LOG.jsonl',{'at':now(),'action':'join_existing_references_after_both_new_seals'})
    result = summarize(old,out,plan)
    check_map(old,old_files)
    check_map(ROOT,new_files)
    write_json(out/'INTEGRITY_GATE.json',{'status':'PASSED','original_files_unchanged':len(old_files),
             'source_hashes_unchanged':len(new_files),'new_executions':0,'model_calls':0,'at':now()},exclusive=True)
    print(json.dumps({'status':result['status'],'dynamic':result['dynamic_vs_static'],'new_executions':0},ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--source-snapshot',required=True,type=Path)
    args = parser.parse_args()
    old,out,snapshot = (p.resolve() for p in (args.old,args.out,args.source_snapshot))
    if ROOT not in out.parents or old==out or old in out.parents:
        raise ValueError('Use a distinct output directory inside this worktree')
    run(old,out,snapshot)
