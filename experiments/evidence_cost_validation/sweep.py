"""Development-only static selection and oracle-free proxy-cost acquisition sweeps."""
import argparse
import gzip
from pathlib import Path
import sys

from experiments.evidence_contract_validation.common import (
    ROOT, CHANNELS, append_json, canonical, frozen_json, load_frozen, now, read_json, sha, write_json)
from experiments.closeout_pilot.evaluation import Worker
from experiments.closeout_pilot.reanalysis import check_map
from .costs import trial
from .statistics import curves


class BoundedWorker(Worker):
    def __init__(self, cwd):
        super().__init__(cwd);self.requests=0;self.ipc_input_bytes=0

    def ask(self, message):
        if len(self.cache)>=30000:self.cache.clear()
        key=sha(canonical(message))
        if key not in self.cache:
            self.requests+=1
            # Exact UTF8 stdin serialization of the inherited worker, not model tokens.
            import json
            self.ipc_input_bytes+=len((json.dumps(message,ensure_ascii=True)+'\n').encode())
        return super().ask(message)


def inputs(out):
    plan=load_frozen(out/'DIAGNOSTIC_PLAN.json');implementation=load_frozen(out/'IMPLEMENTATION_SEAL.json')
    check_map(ROOT,plan['source_hashes']);check_map(ROOT,implementation['source_hashes'])
    for name,key in [('MASK_MANIFEST.json','mask_manifest_sha256'),('COST_CONTRACTS.json','cost_contract_sha256')]:
        assert sha((out/name).read_bytes())==plan[key]
    return plan,load_frozen(out/'MASK_MANIFEST.json')


def minimal(query,condition,budget,rho,pred):
    return {k:query[k] for k in ('query_id','unit','family_id','metric','source_id')} | dict(
        condition=condition['condition'],mechanism=condition['mechanism'],seed=condition['seed'],
        budget=budget,rho=rho,**pred)


def select(out,cost):
    plan,masks=inputs(out);old=ROOT/plan['old_run'];contract=plan['costs'][cost]
    dest=out/cost;dest.mkdir(exist_ok=True)
    if (dest/'STATIC_SEARCH_STARTED.json').exists():raise FileExistsError('Selection is single-use')
    write_json(dest/'STATIC_SEARCH_STARTED.json',dict(at=now(),cost=cost,source='old development only'),exclusive=True)
    docs=read_json(old/'licensed_source/development.json');queries=read_json(old/'development_QUERIES.json')
    truth=read_json(old/'oracle/development.json');worker=BoundedWorker(out/'temp'/cost/'selection')
    tables=[];selected={};count=0
    try:
        for metric in sorted({q['metric'] for q in queries}):
            best=None
            for candidate in [r for r in plan['candidates'] if r['metric']==metric]:
                records=[];wrong=0;charged=0
                for query in [q for q in queries if q['metric']==metric]:
                    for condition in masks['development'][query['query_id']]:
                        initial=set(CHANNELS)-set(condition['missing'])
                        for budget,rho in zip(contract['budgets'],contract['rho']):
                            pred,broker,_=trial(worker,docs[query['unit']],metric,initial,contract,
                                plan['costs']['C0']['quotes'],budget,'metric_static',candidate['order'])
                            records.append(minimal(query,condition,budget,rho,pred));count+=1
                            target=truth[query['query_id']]
                            wrong+=int(target['status']=='point' and pred['status']=='point' and pred['value']!=target['value'])
                            charged+=(broker.total if pred['status']!='infeasible' else 0)*(1/3 if condition['mechanism']=='random' else 1)
                score=curves(records,truth,contract['rho'])
                row=candidate|dict(wrong=wrong,auc=score['auc'],curve=score['aggregate'],
                                   weighted_decision_cost=charged,replay_rows=len(records))
                tables.append(row);append_json(dest/'STATIC_SEARCH_CHECKPOINTS.jsonl',row|dict(at=now()))
                rank=(-wrong,score['auc'] if score['auc'] is not None else 0,-charged,-candidate['candidate_index'])
                if best is None or rank>best[0]:best=(rank,candidate['order'])
            selected[metric]=best[1]
    finally:worker.close()
    write_json(dest/'STATIC_CANDIDATES.json',tables,exclusive=True)
    frozen_json(dest/'SELECTED_STATIC.json',dict(cost=cost,selected=selected,development_only=True,
        candidate_universe_sha256=plan['candidate_sha256'],at=now(),replay_rows=count,
        worker_requests=worker.requests,actual_policy_ipc_input_bytes=worker.ipc_input_bytes,model_calls=0))
    return dict(cost=cost,selected=selected,selection_replay_rows=count)


def replay(out,cost,split):
    plan,masks=inputs(out);old=ROOT/plan['old_run'];contract=plan['costs'][cost]
    dest=out/cost;selected=load_frozen(dest/'SELECTED_STATIC.json')['selected']
    docs=read_json(old/'licensed_source'/f'{split}.json');queries=read_json(old/f'{split}_QUERIES.json')
    predictions=dest/f'{split}_PREDICTIONS.jsonl.gz';ledger=dest/f'{split}_COST_LEDGER.jsonl.gz'
    if predictions.exists() or ledger.exists():raise FileExistsError('Retain every prior replay')
    worker=BoundedWorker(out/'temp'/cost/split);views={};count=0
    try:
        with gzip.open(predictions,'wt',encoding='utf-8') as pf,gzip.open(ledger,'wt',encoding='utf-8') as lf:
            for query in queries:
                for condition in masks[split][query['query_id']]:
                    initial=set(CHANNELS)-set(condition['missing'])
                    for policy in plan['policies']:
                        order=list(CHANNELS) if policy=='global_fixed' else selected[query['metric']]
                        for budget,rho in zip(contract['budgets'],contract['rho']):
                            pred,broker,steps=trial(worker,docs[query['unit']],query['metric'],initial,contract,
                                plan['costs']['C0']['quotes'],budget,policy,order,views,True)
                            feasible=pred['status']!='infeasible';rid=f'{cost}:{split}:{count:07}'
                            record=minimal(query,condition,budget,rho,pred)|dict(row_id=rid,policy=policy,cost_model=cost,split=split,
                                required_initial_cost=broker.initial_cost,decision_total=broker.total if feasible else 0,
                                required_initial_wire_bytes=broker.wire.initial_bytes,wire_bytes=broker.wire.total if feasible else 0,
                                acquired_order=[e['channel'] for e in broker.events if e['kind']=='acquire'] if feasible else [])
                            pf.write(canonical(record).decode()+'\n')
                            lf.write(canonical(dict(row_id=rid,feasible=feasible,events=broker.events if feasible else [],steps=steps,
                                initial_channels=sorted(initial),decision_total=record['decision_total'],wire_bytes=record['wire_bytes'])).decode()+'\n')
                            count+=1
                worker.cache.clear()
                append_json(dest/'REPLAY_CHECKPOINTS.jsonl',dict(at=now(),split=split,rows=count,query_completed=query['query_id'],model_calls=0))
    finally:worker.close()
    view_path=dest/f'{split}_VISIBLE_PROJECTIONS.jsonl.gz'
    with gzip.open(view_path,'wt',encoding='utf-8') as f:
        for digest,view in sorted(views.items()):f.write(canonical(dict(sha256=digest,visible=view)).decode()+'\n')
    frozen_json(dest/f'{split}_TRAJECTORY_SEAL.json',dict(at=now(),rows=count,oracle_joined=False,
        files={p.name:sha(p.read_bytes()) for p in (predictions,ledger,view_path)},
        worker_requests=worker.requests,actual_policy_ipc_input_bytes=worker.ipc_input_bytes,model_calls=0))
    return dict(cost=cost,split=split,rows=count,model_calls=0)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['select','replay']);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--cost',choices=['C1','C2'],required=True);p.add_argument('--split',choices=['development','heldout'])
    a=p.parse_args();out=a.out.resolve();append_json(out/'COMMANDS.jsonl',dict(at=now(),argv=sys.argv,stage=a.stage,cost=a.cost))
    print(select(out,a.cost) if a.stage=='select' else replay(out,a.cost,a.split))
