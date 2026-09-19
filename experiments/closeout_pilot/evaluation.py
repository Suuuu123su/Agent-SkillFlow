"""Budget replay over sealed records. Oracle is not loaded here."""
from __future__ import annotations

import gzip
import itertools
import json
import os
import random
import statistics
import subprocess
import sys
from pathlib import Path

from experiments.evidence_contract_validation.common import CHANNELS, CODE, SEEDS, append_json, canonical, now, sha, write_json
from experiments.evidence_contract_validation.masks import conditions
from experiments.evidence_contract_validation.policy import PRIORITY, complete_order
from experiments.evidence_contract_validation.transport import Broker


class Worker:
    def __init__(self, private_cwd):
        private_cwd.mkdir(parents=True, exist_ok=True)
        environment = {key: value for key, value in os.environ.items()
                       if key in ('SYSTEMROOT', 'WINDIR', 'PATH', 'SystemRoot')}
        environment.update(TEMP=str(private_cwd), TMP=str(private_cwd),
                           PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
        self.process = subprocess.Popen(
            [sys.executable, '-B', '-I', str(Path(__file__).with_name('policy_worker.py'))],
            cwd=private_cwd, env=environment, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        self.cache = {}

    def ask(self, message):
        key = sha(canonical(message))
        if key not in self.cache:
            self.process.stdin.write(json.dumps(message, ensure_ascii=True) + '\n')
            self.process.stdin.flush()
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError('Policy worker stopped: ' + self.process.stderr.read())
            answer = json.loads(line)
            if 'error' in answer:
                raise ValueError(answer['error'])
            self.cache[key] = answer
        return self.cache[key]

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=30)
        error = self.process.stderr.read()
        self.process.stdout.close()
        self.process.stderr.close()
        if self.process.returncode:
            raise RuntimeError(error)


def evaluate_one(worker, document, metric, visible, quotes, budget, policy, order):
    broker = Broker(document, visible, quotes)
    initial = broker.total
    if initial > budget:
        return {'status': 'infeasible', 'value': None, 'missing_channels': [],
                'reason': 'budget_below_common_initial_payload'}, broker
    while True:
        result = worker.ask({'metric': metric, 'visible': broker.visible,
                             'policy': policy, 'acquired': sorted(broker.acquired),
                             'order': order, 'quotes': quotes,
                             'remaining': budget - broker.total})
        if result['selected'] is None:
            return result['prediction'], broker
        broker.acquire(result['selected'], budget)


def orders_for(metric, selected, include_dynamic):
    result = [('global_fixed', list(CHANNELS))]
    for seed in SEEDS:
        order = list(CHANNELS)
        random.Random(seed).shuffle(order)
        result.append(('random_' + str(seed), order))
    result.append(('metric_static', selected[metric]))
    if include_dynamic:
        result.append(('dependency_guided', selected[metric]))
    return result


def candidate_orders(metric, quotes, greedy_orders=()):
    relevant = PRIORITY[metric]
    candidates = []
    for order in [complete_order(relevant), complete_order(sorted(relevant, key=lambda c:(quotes[c],c))), *greedy_orders]:
        if order not in candidates:
            candidates.append(order)
    # Round-robin leading channels; no receipt-first truncation bias.
    pools = [list(itertools.permutations([c for c in relevant if c != first])) for first in relevant]
    for depth in range(max(map(len, pools))):
        for first, pool in zip(relevant, pools):
            if depth < len(pool):
                order = complete_order([first, *pool[depth]])
                if order not in candidates:
                    candidates.append(order)
                if len(candidates) == 24:
                    return candidates
    return candidates


def greedy_order(metric, documents, queries, truth, quotes, per_byte):
    from experiments.evidence_contract_validation.dependencies import project
    from .predictor import predict
    remaining = complete_order(PRIORITY[metric])
    chosen = []
    while remaining:
        scores = []
        for channel in remaining:
            gains = []
            for query in queries:
                if query['metric'] != metric or truth[query['query_id']]['status'] != 'point':
                    continue
                doc = documents[query['unit']]
                for missing in [set(CHANNELS), *({name} for name in CHANNELS)]:
                    start = (set(CHANNELS) - missing) | set(chosen)
                    before = predict(metric, project(doc, start))
                    after = predict(metric, project(doc, start | {channel}))
                    target = truth[query['query_id']]['value']
                    gains.append(int(after['status']=='point' and after['value']==target) - int(before['status']=='point' and before['value']==target))
            gain = statistics.mean(gains) if gains else 0
            scores.append(gain / quotes[channel] if per_byte else gain)
        index = max(range(len(remaining)), key=lambda i:(scores[i],-i))
        chosen.append(remaining.pop(index))
    return chosen


def choose_static(documents, queries, quotes, budgets, truth, cwd, frozen_candidates):
    """Original candidate list; development only; error-first normalized AUC."""
    from experiments.evidence_contract_validation.reporting import _auc
    worker = Worker(cwd)
    selected, table = {}, []
    try:
        for metric in sorted({q['metric'] for q in queries}):
            candidates = [c for c in frozen_candidates if c['metric'] == metric]
            if not candidates or len(candidates) > 24:
                raise ValueError('Original candidate universe missing or too large')
            best = None
            for candidate in candidates:
                index, order = candidate['candidate_index'], candidate['order']
                wrong, cost, n = 0, 0, 0
                family_scores = {}
                for query in queries:
                    if query['metric'] != metric:
                        continue
                    doc = documents[query['unit']]
                    for condition in conditions(query['unit'], query['fault_event']):
                        visible = set(CHANNELS) - set(condition['missing'])
                        for budget in budgets:
                            pred, broker = evaluate_one(worker, doc, metric, visible, quotes,
                                                        budget, 'metric_static', order)
                            oracle = truth[query['query_id']]
                            comparable = oracle['status'] == 'point'
                            good = comparable and pred['status'] == 'point' and pred['value'] == oracle['value']
                            bad = comparable and pred['status'] == 'point' and pred['value'] != oracle['value']
                            wrong += int(bad)
                            weight = 1/3 if condition['mechanism'] == 'random' else 1
                            cost += (broker.total if pred['status'] != 'infeasible' else 0) * weight
                            n += 1
                            scores = family_scores.setdefault((query['family_id'], budget), [0, 0])
                            scores[0] += int(good) * weight
                            scores[1] += int(comparable) * weight
                curve = []
                for budget in budgets:
                    values = [a/b for (f, x), (a,b) in family_scores.items() if x == budget and b]
                    curve.append({'budget':budget, 'coverage':statistics.mean(values) if values else None})
                area = _auc(curve, 'budget', 'coverage', budgets)
                row = {'metric':metric, 'candidate_index':index, 'order':order, 'wrong':wrong,
                       'family_equal_coverage_auc':area, 'curve':curve,
                       'total_charged_bytes':cost, 'replay_rows':n}
                table.append(row)
                append_json(cwd.parent / 'STATIC_SEARCH_CHECKPOINTS.jsonl', row | {'at':now()})
                score = (-wrong, area if area is not None else 0, -cost, -index)
                if best is None or score > best[0]:
                    best = score, order
            selected[metric] = best[1]
    finally:
        worker.close()
    return selected, table


def replay(out, split, documents, queries, freeze):
    """Write prediction/cost files first; do not read oracle or Full at any point."""
    predictions = out / f'{split}_PREDICTIONS.jsonl.gz'
    costs = out / f'{split}_COST_LEDGER.jsonl.gz'
    if predictions.exists() or costs.exists():
        raise FileExistsError('Replay is single-use; preserve previous outputs')
    worker = Worker(out / 'policy_ipc' / split)
    count, cost_rows = 0, 0
    try:
        with gzip.open(predictions, 'wt', encoding='utf-8') as pf, gzip.open(costs, 'wt', encoding='utf-8') as cf:
            for q_index, query in enumerate(queries):
                doc = documents[query['unit']]
                for condition in conditions(query['unit'], query['fault_event']):
                    visible = set(CHANNELS) - set(condition['missing'])
                    for policy, order in orders_for(query['metric'], freeze['selected_static'], freeze['run_dynamic']):
                        for budget in freeze['budgets']:
                            pred, broker = evaluate_one(worker, doc, query['metric'], visible,
                                                        freeze['quotes'], budget, policy, order)
                            rid = f'{split}:{count:07d}'
                            row = {key: query[key] for key in ('query_id', 'unit', 'family_id', 'metric', 'source_id')}
                            row.update(split=split, row_id=rid, condition=condition['condition'],
                                       mechanism=condition['mechanism'], seed=condition['seed'],
                                       policy=policy, budget=budget, **pred,
                                       initial_bytes=broker.initial_bytes,
                                       charged_total_bytes=broker.total if pred['status'] != 'infeasible' else 0,
                                       required_initial_bytes=broker.initial_bytes,
                                       visible_json_bytes=len(canonical(broker.visible)),
                                       acquired_channels=len(broker.acquired),
                                       acquired_order=[x['channel'] for x in broker.events if x['kind'] == 'acquire'],
                                       evidence_fields=_fields(broker.visible),
                                       evidence_events=_events(broker.visible))
                            pf.write(canonical(row).decode() + '\n')
                            cf.write(canonical({'row_id': rid, 'feasible': pred['status'] != 'infeasible',
                                                'events': broker.events if pred['status'] != 'infeasible' else [], 'initial_bytes': broker.initial_bytes,
                                                'required_untransmitted_initial_bytes': broker.initial_bytes if pred['status'] == 'infeasible' else 0,
                                                'charged_total_bytes': row['charged_total_bytes']}).decode() + '\n')
                            count += 1
                            cost_rows += 1
                            if count % 500 == 0:
                                pf.flush()
                                cf.flush()
                                append_json(out / 'CHECKPOINTS.jsonl', {'split': split, 'rows': count,
                                            'queries_complete': q_index, 'at': now(), 'model_calls': 0})
                worker.cache.clear()
    finally:
        worker.close()
    write_json(out / f'{split}_TRAJECTORY_SEAL.json',
               {'sealed_at': now(), 'oracle_joined': False, 'rows': count,
                'prediction_sha256': sha(predictions.read_bytes()),
                'cost_ledger_sha256': sha(costs.read_bytes())}, exclusive=True)
    return count


def _fields(value):
    if isinstance(value, dict):
        return sum(_fields(v) for v in value.values())
    if isinstance(value, list):
        return sum(_fields(v) for v in value)
    return int(value is not None)


def _events(value):
    if isinstance(value, dict):
        return sum(len(v) if k in ('records', 'events', 'receipts') and isinstance(v, list)
                   else _events(v) for k, v in value.items())
    if isinstance(value, list):
        return sum(_events(v) for v in value)
    return 0
