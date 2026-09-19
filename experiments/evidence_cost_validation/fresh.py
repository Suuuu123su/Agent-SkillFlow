"""Gate-controlled four-cell fresh collection, using frozen adapter/oracle semantics."""
import argparse
import copy
import json
from pathlib import Path
import random
import sys

from experiments.evidence_contract_validation.common import (
    ROOT, CHANNELS, append_json, canonical, frozen_json, load_frozen, now, read_json, sha, write_json)
from experiments.evidence_contract_validation.sandbox import load_registry, _spec, _artifact
from experiments.evidence_contract_validation.adapter import adapt,query_records
from experiments.evidence_contract_validation.independent_oracle import evaluate_unit
from experiments.evidence_contract_validation.dependencies import project,restoration_bundle
from experiments.evidence_contract_validation.transport import padded_packet
from experiments.closeout_pilot.predictor import predict
from experiments.closeout_pilot.reanalysis import check_map,file_map
from .fresh_runner import run_unit
from .sweep import inputs


def source_hashes():
    mapping={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in Path(__file__).parent.glob('*.py')}
    for name in ('sandbox.py','adapter.py','independent_oracle.py','dependencies.py','dependency_contract.json','policy.py','masks.py'):
        p=ROOT/'experiments/evidence_contract_validation'/name;mapping[p.relative_to(ROOT).as_posix()]=sha(p.read_bytes())
    p=ROOT/'experiments/closeout_pilot/predictor.py';mapping[p.relative_to(ROOT).as_posix()]=sha(p.read_bytes())
    return mapping


def make_spec(family_id,uid,n,cell):
    family=next(f for f in load_registry()['families'] if f['family_id']==family_id)
    base=_spec(family|{'variants':['normal']*n},n-1);old_id=base['execution_unit_id']
    def rename(v):
        if isinstance(v,dict):return {k:rename(x) for k,x in v.items()}
        if isinstance(v,list):return [rename(x) for x in v]
        return v.replace(old_id,uid) if isinstance(v,str) else v
    spec=rename(base);spec.update(execution_unit_id=uid,split='heldout',variant='normal',
        grant_variant='wrong_scope' if cell.startswith('invalid') else 'normal',
        execution_variant='no_commit' if cell.endswith('no_commit') else 'normal')
    op=spec['operation'];requirements=spec['task_requirements']
    if op=='append_journal':
        spec['initial_files']['journal.txt']=f'opening={100+n}\nverified-prefix=fresh-20260919\n'
        requirements['artifacts']=[_artifact('journal.txt',(spec['initial_files']['journal.txt']+spec['entry']).encode())]
    elif op=='manifest_package':
        package=canonical({'items':json.loads(spec['initial_files']['items.json']),'version':n})
        requirements['artifacts']=[_artifact('package.json',package),_artifact('manifest.json',canonical(dict(artifact='package.json',sha256=sha(package),count=2,task_id=spec['task_id'])))]
    elif op=='inventory_reservation':
        spec['initial_sql'][-1]="INSERT INTO stock VALUES('bolt',60),('nut',80),('spare',120)"
        requirements['database_checks'][0]['expected_rows']=[['bolt',60-n],['nut',80-2*n],['spare',120]]
    # These six old operations have one supervised business-program invocation.
    # Their internal writes/SQL are implementation details, not repeated task attempts.
    spec['registered_supervised_actions']=1
    return spec


def new_conditions(uid,fault,seeds):
    result=[dict(condition='channel_'+c,mechanism='whole_channel',seed=0,missing=[c]) for c in CHANNELS]
    result.append(dict(condition='channel_receipt_lifecycle',mechanism='whole_channel',seed=0,missing=['receipt','lifecycle']))
    for seed in seeds:
        for count in (1,3,5):
            rng=random.Random(str(seed)+'|'+uid+'|'+str(count))
            result.append(dict(condition='random_'+str(count),mechanism='random',seed=seed,missing=sorted(rng.sample(CHANNELS,count))))
    result.append(dict(condition='failure_correlated',mechanism='failure_stress',seed=0,
                       missing=['receipt','lifecycle','failure'] if fault else ['decision_reason']))
    return result


def counted(out,spec,phase,attempt=1):
    ledger=out/'EXECUTION_LEDGER.jsonl';entries=[json.loads(s) for s in ledger.read_text('utf-8').splitlines() if s]
    assert len(entries)<48 and attempt<=2
    previous=[r for r in entries if r['unit_id']==spec['execution_unit_id']]
    assert len(previous)==attempt-1
    if phase=='sanity':assert sum(r['phase']=='sanity' for r in entries)<4
    elif attempt==1:assert sum(r['phase']=='formal' and r['attempt']==1 for r in entries)<24
    else:assert sum(r['attempt']==2 for r in entries)<20
    ordinal=len(entries)+1;aid=f'attempt-{attempt:02}'
    append_json(ledger,dict(ordinal=ordinal,at=now(),phase=phase,unit_id=spec['execution_unit_id'],attempt=attempt,
                           supervised_action_cap=16,registered_actions=1,model_calls=0,state='COUNTED_BEFORE_INITIALIZATION'))
    raw=out/('sanity/raw' if phase=='sanity' else 'fresh/raw')
    record=run_unit(spec,raw,aid)
    folder=raw/spec['execution_unit_id']/aid
    independent=evaluate_unit(folder);write_json(folder/'INDEPENDENT_ORACLE.json',independent,exclusive=True)
    infrastructure=record['supervisor']['timed_out'] or record['supervisor']['process_returncode'] not in (0,17)
    write_json(folder/'ATTEMPT_RESULT.json',dict(status='INFRASTRUCTURE_FAILED' if infrastructure else 'COMPLETED',
               ordinal=ordinal,registered_actions=1,supervisor_actions=1,worker_process_calls=1,
               return_code=record['supervisor']['process_returncode'],planned_no_commit=spec['execution_variant']=='no_commit',
               effects=len(record['supervisor']['side_effect_records']),independent_truth=independent['metrics'],model_calls=0),exclusive=True)
    return record,independent,folder,infrastructure


def sanity(out):
    plan,_=inputs(out);assert load_frozen(out/'GATE_A.json')['passed']
    directory=out/'sanity';directory.mkdir(exist_ok=False)
    cells=[('D01_append_journal','valid_commit'),('D01_append_journal','invalid_no_commit'),
           ('H02_inventory_reservation','invalid_commit'),('H02_inventory_reservation','valid_no_commit')]
    specs=[make_spec(f,f'S{i+1:05}',15+i,c) for i,(f,c) in enumerate(cells)]
    frozen_json(directory/'SANITY_PLAN.json',dict(at=now(),specs=specs,cells=cells,source_hashes=source_hashes(),
                 gate_A_sha256=sha((out/'GATE_A.json').read_bytes()),purpose='Interface/truth check only; no policy tuning'))
    checks=[]
    for spec,(_,cell) in zip(specs,cells,strict=True):
        record,truth,folder,failed=counted(out,spec,'sanity')
        assert not failed,'Sanity infrastructure failure retained; stop'
        doc=adapt(record);full={m:predict(m,project(doc,set(CHANNELS))) for m in ('UEA','TaskSuccess')}
        expected={'UEA':cell=='invalid_commit','TaskSuccess':cell.endswith('commit') and not cell.endswith('no_commit')}
        for metric,value in expected.items():
            assert truth['metrics'][metric]['status']=='point' and truth['metrics'][metric]['value']==value
            assert full[metric]['status']=='point' and full[metric]['value']==value,'Semantic mismatch; stop, never tune predictor'
        # Existing packet capacity is checked, not recalibrated.
        quotes=plan['costs']['C0']['quotes']
        for c in CHANNELS:
            for acquired in (set(),set(CHANNELS)-{c}):padded_packet(restoration_bundle(doc,acquired,[c]),quotes[c])
        checks.append(dict(unit_id=spec['execution_unit_id'],cell=cell,oracle_matches_actual_effect=True,
                           full_agreement=True,packet_capacity_supported=True,raw=folder.relative_to(out).as_posix()))
    frozen_json(directory/'SANITY_RESULTS.json',dict(status='PASSED',checks=checks,actual_executions=4,model_calls=0))
    print(dict(stage='sanity',status='PASSED',executions=4,model_calls=0))


def freeze(out):
    plan,_=inputs(out);assert load_frozen(out/'GATE_A.json')['passed']
    assert load_frozen(out/'sanity/SANITY_RESULTS.json')['status']=='PASSED'
    directory=out/'fresh';directory.mkdir(exist_ok=False)
    rng=random.Random(plan['fresh_selection']['input_seed']);specs=[];schedule=[]
    for family in plan['fresh_selection']['families']:
        n=rng.randint(5,14)
        for cell in plan['fresh_selection']['cells']:
            uid=f'N{len(specs)+1:05}';spec=make_spec(family,uid,n,cell);specs.append(spec)
            schedule.append(dict(unit_id=uid,family_id=family,cell=cell,input_sha256=sha(canonical(spec))))
    assert len(specs)==24 and len({s['execution_unit_id'] for s in specs})==24
    source=source_hashes()
    # Sanity must not have changed any collector/predictor/oracle implementation.
    check_map(ROOT,load_frozen(out/'sanity/SANITY_PLAN.json')['source_hashes'])
    frozen_json(out/'FRESH_PLAN.json',dict(at=now(),specs=specs,schedule=schedule,source_hashes=source,
        diagnostic_plan_sha256=sha((out/'DIAGNOSTIC_PLAN.json').read_bytes()),gate_A_sha256=sha((out/'GATE_A.json').read_bytes()),
        costs=plan['costs'],static_orders={c:load_frozen(out/c/'SELECTED_STATIC.json') for c in ('C1','C2')},
        seeds=plan['fresh_missing_seeds'],gate_B=plan['gate_B'],resources=plan['resources'],
        contract='controlled-persistent-effect-v1',same_author_selection_bias=True,
        supervised_action='one real worker program invocation per unit; internal writes/SQL not separate scene executions',
        independent_truth='retained files/SQLite read by unmodified independent_oracle; no predictor/full used for truth',
        protocol='collect all 24 once, seal raw and oracle, generate one mask manifest, seal predictions before evaluator joins truth'))
    print(dict(stage='freeze',formal_units=24,actual_executions=4,model_calls=0))


def collect(out):
    plan=load_frozen(out/'FRESH_PLAN.json');check_map(ROOT,plan['source_hashes'])
    assert load_frozen(out/'GATE_A.json')['passed'];directory=out/'fresh'
    if (directory/'COLLECTION_STARTED.json').exists():raise FileExistsError('One confirmation batch only')
    write_json(directory/'COLLECTION_STARTED.json',dict(at=now(),plan_sha256=sha((out/'FRESH_PLAN.json').read_bytes())),exclusive=True)
    documents={};queries=[];truth={};completed=[]
    for spec in plan['specs']:
        record,independent,folder,failed=counted(out,spec,'formal')
        if failed:
            record,independent,folder,failed=counted(out,spec,'formal',2)
            if failed:raise RuntimeError('Infrastructure retry exhausted; retain incomplete batch')
        documents[spec['execution_unit_id']]=adapt(record)
        qq=query_records(record);assert len(qq)==2
        queries.extend(qq)
        for q in qq:truth[q['query_id']]=independent['metrics'][q['metric']]
        completed.append(dict(unit_id=spec['execution_unit_id'],raw=folder.relative_to(directory).as_posix(),
                              independent_truth=independent['metrics'],effects=len(record['supervisor']['side_effect_records'])))
        append_json(directory/'COMPLETED.jsonl',completed[-1]|dict(at=now()))
    frozen_json(directory/'RAW_AND_ORACLE_SEAL.json',dict(at=now(),files=file_map(directory/'raw'),scope='all retained raw attempts'))
    write_json(directory/'licensed_source/heldout.json',documents,exclusive=True)
    write_json(directory/'heldout_QUERIES.json',queries,exclusive=True)
    write_json(directory/'oracle/heldout.json',truth,exclusive=True)
    # Adapter query fault_event stays only in this evaluator-side mask generation.
    masks={'heldout':{q['query_id']:new_conditions(q['unit'],q['fault_event'],plan['seeds']) for q in queries}}
    frozen_json(directory/'MASK_MANIFEST.json',masks)
    frozen_json(directory/'DATASET_SEAL.json',dict(at=now(),files={rel:sha((directory/rel).read_bytes()) for rel in
        ['licensed_source/heldout.json','heldout_QUERIES.json','oracle/heldout.json','MASK_MANIFEST.json']},formal_units=24,primary_queries=48))
    parent=load_frozen(out/'DIAGNOSTIC_PLAN.json')
    # The same frozen sweep/audit code consumes a derived dataset binding; no
    # optimization or policy change. The original diagnostic plan remains intact.
    derived=parent|dict(fresh_dataset=True,binding_created_at=now(),fresh_plan_sha256=sha((out/'FRESH_PLAN.json').read_bytes()),old_run=directory.relative_to(ROOT).as_posix(),
        parent_diagnostic_plan_sha256=sha((out/'DIAGNOSTIC_PLAN.json').read_bytes()),
        mask_manifest_sha256=sha((directory/'MASK_MANIFEST.json').read_bytes()))
    frozen_json(directory/'DIAGNOSTIC_PLAN.json',derived)
    for name in ('COST_CONTRACTS.json','COST_CONTRACTS.json.sha256','IMPLEMENTATION_SEAL.json','IMPLEMENTATION_SEAL.json.sha256'):
        (directory/name).write_bytes((out/name).read_bytes())
    for cost in ('C1','C2'):
        (directory/cost).mkdir()
        for name in ('SELECTED_STATIC.json','SELECTED_STATIC.json.sha256'):(directory/cost/name).write_bytes((out/cost/name).read_bytes())
    frozen_json(directory/'COLLECTION_COMPLETE.json',dict(at=now(),units=24,queries=48,model_calls=0,
        attempts=len([s for s in (out/'EXECUTION_LEDGER.jsonl').read_text('utf-8').splitlines() if s])))
    print(dict(stage='collect',units=24,queries=48,model_calls=0))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['sanity','freeze','collect']);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve();append_json(out/'COMMANDS.jsonl',dict(at=now(),argv=sys.argv,stage=a.stage))
    globals()[a.stage](out)
