"""Independent, read-only delivery audit; standard library, no core imports.

Usage: python -B verify_delivery.py RUN_DIRECTORY [--development-only]
Writes JSON only to stdout. It never runs a task, predictor, oracle, or policy.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
import csv
from datetime import datetime
import gzip
import hashlib
from itertools import zip_longest
import json
from pathlib import Path
import statistics
import sys

REPO = Path(__file__).resolve().parents[3]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def frozen(path):
    require(path.is_file(), 'Missing frozen file: ' + str(path))
    actual = digest(path.read_bytes())
    expected = Path(str(path) + '.sha256').read_text(encoding='ascii').strip()
    require(actual == expected, 'Frozen SHA mismatch: ' + str(path))
    return read_json(path)


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def confined(root, relative):
    path = (root / relative).resolve()
    require(root.resolve() in path.parents, 'Manifest path escapes root: ' + relative)
    return path


def audit_split_inputs(out, split, registration, family_split):
    manifest = frozen(out / f'{split}_INPUT_MANIFEST.json')
    required_paths = {p.relative_to(out).as_posix() for p in (out/'raw'/split).rglob('*') if p.is_file()}
    required_paths.update({f'licensed_source/{split}.json', f'{split}_QUERIES.json', f'{split}_QUERY_REGISTRY.csv'})
    require(set(manifest) == required_paths, f'{split}: input manifest lacks files or has unregistered extras')
    for relative, expected in manifest.items():
        require(digest(confined(out, relative).read_bytes()) == expected, 'Input changed: ' + relative)
    seal = frozen(out / f'{split}_COLLECTION_SEAL.json')
    source = out / 'licensed_source' / f'{split}.json'
    require(digest(source.read_bytes()) == seal['document_sha256'], split + ': licensed source hash mismatch')
    records = sorted((out/'raw'/split).rglob('record.json'))
    require(len(records) == seal['units'] == 24, split + ': raw unit count is not 24')
    require(len(seal['records']) == 24, split + ': collection record count differs')
    sealed_records = {item['unit']: item for item in seal['records']}
    family_ids = {f['family_id'] for f in family_split['families'] if f['split'] == split}
    units = set()
    for path in records:
        raw = read_json(path)
        unit = raw['execution_unit_id']
        require(unit not in units, split + ': repeated raw unit')
        units.add(unit)
        require(raw['family_id'] in family_ids and raw['split'] == split, 'Raw family/split mismatch: ' + unit)
        item = sealed_records[unit]
        require((out/item['path']).resolve() == path.resolve(), 'Raw path disagrees with seal: ' + unit)
        require(digest(path.read_bytes()) == item['sha256'], 'Raw record digest mismatch: ' + unit)
        spec = read_json(path.parent/'spec.json')
        original_spec = {k: v for k, v in spec.items() if not k.startswith('_')}
        require(digest(canonical(original_spec)) == registration['spec_hashes'][unit], 'Unit spec changed: ' + unit)
        sup = raw['supervisor']
        for name, value in [('before.json', sup['state_before']), ('after.json', sup['state_after']),
                            ('permission_schedule.json', raw['permission_schedule']),
                            ('task_requirements.json', raw['task_requirements'])]:
            require(read_json(path.parent/name) == value, 'Sidecar differs from sealed record: ' + unit + '/' + name)
        for phase in ('state_before', 'state_after'):
            for name, record in sup[phase].items():
                data = base64.b64decode(record['content_base64'], validate=True)
                require(digest(data) == record['sha256'] and len(data) == record['size_bytes'], 'Snapshot bytes invalid: ' + unit + '/' + name)
        stored = {p.relative_to(path.parent/'sandbox').as_posix(): digest(p.read_bytes())
                  for p in (path.parent/'sandbox').rglob('*') if p.is_file()}
        require(stored == {name: v['sha256'] for name, v in sup['state_after'].items()}, 'Actual sandbox differs from after-state: ' + unit)
        changed = {name for name in set(sup['state_before']) | set(sup['state_after'])
                   if sup['state_before'].get(name, {}).get('sha256') != sup['state_after'].get(name, {}).get('sha256')}
        require(changed == {item['path'] for item in sup['side_effect_records']}, 'Side-effect path set mismatch: ' + unit)
        require(bool(changed) == sup['committed_effect'], 'Effect flag disagrees with actual bytes: ' + unit)
        journal = read_lines(path.parent/'supervisor.jsonl')
        require([event['event'] for event in journal] == ['attempt_registered', 'action_started', 'action_joined'], 'Supervisor interval malformed: ' + unit)
        require(journal[0]['time_ns'] <= journal[1]['time_ns'] <= journal[2]['time_ns'], 'Nonmonotonic action: ' + unit)
        require(journal[1]['time_ns'] == raw['attempt']['started_ns'] and journal[2]['time_ns'] == raw['attempt']['finished_ns'], 'Action clock duplicate differs: ' + unit)
        require(journal[2]['effect_id'] == sup['effect_id'] == raw['attempt']['effect_id'], 'Effect ID duplicate differs: ' + unit)
    queries = read_json(out/f'{split}_QUERIES.json')
    qmap = {q['query_id']: q for q in queries}
    require(len(qmap) == len(queries) == seal['queries'], 'Query identity/count mismatch: ' + split)
    require({q['unit'] for q in queries} == units and len({q['family_id'] for q in queries}) == 6, 'Query unit/family coverage mismatch')
    with (out/f'{split}_QUERY_REGISTRY.csv').open(encoding='utf-8-sig', newline='') as stream:
        csv_rows = list(csv.DictReader(stream))
    require(len(csv_rows) == len(queries), 'CSV query count mismatch')
    for a, b in zip(queries, csv_rows):
        require(all(str(a[k]) == b[k] for k in b), 'CSV/JSON query registry disagreement')
    return {'units': units, 'queries': qmap, 'manifest_files': len(manifest), 'raw_records': len(records)}


def audit_trajectories(out, split, plan, query_map, oracle):
    seal = read_json(out/f'{split}_TRAJECTORY_SEAL.json')
    pp = out/f'{split}_PREDICTIONS.jsonl.gz'
    cp = out/f'{split}_COST_LEDGER.jsonl.gz'
    require(digest(pp.read_bytes()) == seal['prediction_sha256'], split + ': prediction seal mismatch')
    require(digest(cp.read_bytes()) == seal['cost_ledger_sha256'], split + ': cost seal mismatch')
    policies = {'global_fixed', 'metric_static', *('random_' + str(s) for s in plan['policy_seeds'])}
    if plan['run_dynamic']:
        policies.add('dependency_guided')
    conditions = {(f'channel_{c}', 0) for c in plan['quotes']}
    conditions.add(('channel_receipt_lifecycle', 0))
    conditions.add(('failure_correlated', 0))
    conditions.update((f'random_{size}', seed) for size in (1, 3, 5) for seed in plan['missing_seeds'])
    expected_rows = len(query_map) * len(conditions) * len(policies) * len(plan['budgets'])
    seen = set()
    initials = {}
    statuses = Counter()
    collapsed = defaultdict(lambda: [0, 0, 0, 0, 0, 0, 0])
    wrong_examples = []
    rows = events_checked = 0
    with gzip.open(pp, 'rt', encoding='utf-8') as pf, gzip.open(cp, 'rt', encoding='utf-8') as cf:
        for index, (p_line, c_line) in enumerate(zip_longest(pf, cf)):
            require(p_line is not None and c_line is not None, 'Prediction and cost file lengths differ')
            p, c = json.loads(p_line), json.loads(c_line)
            rid = f'{split}:{index:07d}'
            require(p['row_id'] == c['row_id'] == rid, 'Mismatched, repeated or out-of-order row_id')
            require(p['query_id'] in query_map, 'Unregistered query')
            q = query_map[p['query_id']]
            require(all(p[k] == q[k] for k in ('unit', 'family_id', 'metric', 'source_id')), 'Prediction metadata differs from frozen query')
            require(p['split'] == split and p['policy'] in policies and p['budget'] in plan['budgets'], 'Unregistered split/policy/budget')
            require((p['condition'], p['seed']) in conditions, 'Unregistered condition/seed')
            key = (p['query_id'], p['policy'], p['budget'], p['condition'], p['seed'])
            require(key not in seen, 'Duplicate repeated-measurement key')
            seen.add(key)
            initial = p['initial_bytes']
            require(initial == p['required_initial_bytes'] == c['initial_bytes'], 'Initial cost fields disagree')
            common_key = (p['unit'], p['condition'], p['seed'])
            require(initials.setdefault(common_key, initial) == initial, 'Policies/metrics/budgets use different initial evidence costs')
            charge = p['charged_total_bytes']
            require(charge == c['charged_total_bytes'], 'Prediction cost differs from ledger')
            feasible = p['status'] != 'infeasible'
            require(c['feasible'] == feasible, 'Feasibility disagrees')
            if not feasible:
                require(charge == 0 and c['events'] == [] and c['required_untransmitted_initial_bytes'] == initial,
                        'Infeasible row charged or silently transmitted evidence')
                require(initial > p['budget'], 'Spurious infeasible result')
            else:
                require(initial <= charge <= p['budget'] and c['required_untransmitted_initial_bytes'] == 0, 'Budget limit violated')
                running = 0
                initial_sum = 0
                acquired = []
                used_channels = set()
                acquisition_started = False
                require(c['events'] and c['events'][0]['kind'] == 'public_header', 'Missing charged public header')
                for event_index, event in enumerate(c['events']):
                    require(type(event['bytes']) is int and event['bytes'] > 0, 'Invalid charge event size')
                    running += event['bytes']
                    require(event['total'] == running, 'Cumulative cost event breaks conservation')
                    require(len(event['sha256']) == 64, 'Missing packet digest')
                    if event['kind'] == 'public_header':
                        require(event_index == 0 and event['channel'] is None, 'Header repeated')
                        initial_sum += event['bytes']
                    else:
                        channel = event['channel']
                        require(channel in plan['quotes'] and event['bytes'] == plan['quotes'][channel], 'Packet differs from frozen fixed quote')
                        require(channel not in used_channels, 'Same evidence channel retransmitted without explicit cache contract')
                        used_channels.add(channel)
                        if event['kind'] == 'initial':
                            require(not acquisition_started, 'Initial evidence appears after an acquisition')
                            initial_sum += event['bytes']
                        else:
                            require(event['kind'] == 'acquire', 'Unknown ledger event')
                            acquisition_started = True
                            acquired.append(channel)
                    events_checked += 1
                require(running == charge and initial_sum == initial, 'Initial or total bytes not conserved')
                require(acquired == p['acquired_order'] and len(used_channels) == p['acquired_channels'], 'Acquisition summary differs from ledger')
            o = oracle[p['query_id']]
            oracle_point = o['status'] == 'point'
            answered = oracle_point and p['status'] == 'point'
            correct = answered and p['value'] == o['value']
            wrong = answered and p['value'] != o['value']
            wrong_safe = wrong and p['metric'] == 'UEA' and p['value'] in (0, False)
            if wrong and len(wrong_examples) < 20:
                wrong_examples.append({'row_id': rid, 'query_id': p['query_id'], 'prediction': p['value'], 'oracle': o['value']})
            statuses[p['status']] += 1
            policy_family = 'random' if p['policy'].startswith('random_') else p['policy']
            group = (p['family_id'], p['query_id'], p['metric'], p['condition'], policy_family, p['budget'])
            row = collapsed[group]
            for j, value in enumerate((1, oracle_point, correct, wrong, answered, wrong_safe, p['status'] == 'point')):
                row[j] += int(value)
            rows += 1
    require(rows == expected_rows == seal['rows'], f'{split}: replay matrix is incomplete')
    family_totals = defaultdict(lambda: [0.0] * 6)
    for (family, qid, metric, condition, policy, budget), values in collapsed.items():
        repeats = values[0]
        expected_repeats = (3 if condition.startswith('random_') else 1) * (3 if policy == 'random' else 1)
        require(repeats == expected_repeats, 'Seed count differs before within-query averaging')
        sums = family_totals[(family, policy, budget)]
        for j in range(6):
            sums[j] += values[j + 1] / repeats
    curves = []
    for policy in sorted({'random' if p.startswith('random_') else p for p in policies}):
        for budget in sorted(plan['budgets']):
            fs = [v for (f, p, b), v in family_totals.items() if p == policy and b == budget]
            require(len(fs) == 6, 'Family aggregation omitted a family')
            covered = [v[1] / v[0] for v in fs if v[0]]
            wrong = [v[2] / v[0] for v in fs if v[0]]
            selective = [v[2] / v[3] for v in fs if v[3]]
            curves.append({'split': split, 'policy': policy, 'budget': budget,
                           'correct_coverage': statistics.mean(covered), 'wrong_point_rate': statistics.mean(wrong),
                           'selective_error_rate': statistics.mean(selective) if selective else None})
    auc = {}
    for policy in sorted({r['policy'] for r in curves}):
        points = [r for r in curves if r['policy'] == policy]
        auc[policy] = sum((b['budget']-a['budget'])*(a['correct_coverage']+b['correct_coverage'])/2
                          for a, b in zip(points, points[1:])) / (points[-1]['budget']-points[0]['budget'])
    return {'rows': rows, 'events_verified': events_checked, 'statuses': dict(statuses),
            'wrong_point_rows': sum(v[3] for v in collapsed.values()),
            'wrong_safe_rows': sum(v[5] for v in collapsed.values()), 'wrong_examples': wrong_examples,
            'family_equal_correct_coverage_auc': auc, 'family_equal_curves': curves,
            'uncompressed_prediction_sha256': _uncompressed_digest(pp),
            'uncompressed_cost_sha256': _uncompressed_digest(cp)}


def _uncompressed_digest(path):
    result = hashlib.sha256()
    with gzip.open(path, 'rb') as stream:
        while True:
            block = stream.read(1024*1024)
            if not block:
                return result.hexdigest()
            result.update(block)


def verify(out, development_only):
    registration = frozen(out/'REGISTRATION.json')
    family_split = frozen(out/'FAMILY_SPLIT.json')
    require(registration['model_call_cap'] == 0 and registration['actual_execution_cap'] == 192, 'Resource contract changed')
    attempts = read_lines(out/'ATTEMPTS.jsonl')
    require(len(attempts) <= 192, 'Actual execution cap exceeded')
    counts = Counter(a['unit'] for a in attempts)
    require(all(n <= 4 for n in counts.values()), 'Per-unit execution cap exceeded')
    require([a['actual_execution_ordinal'] for a in attempts] == list(range(1, len(attempts)+1)), 'Attempt sequence not contiguous')
    require(all(a['model_calls'] == 0 and a['state'] == 'COUNTED_BEFORE_INITIALIZATION' for a in attempts), 'Attempt budget registration incorrect')
    splits = ['development'] if development_only else ['development', 'heldout']
    inputs = {split: audit_split_inputs(out, split, registration, family_split) for split in splits}
    for split in splits:
        split_attempts = [a for a in attempts if a['split'] == split]
        require({a['unit'] for a in split_attempts} == inputs[split]['units'], 'Attempt/raw unit mismatch')
    result = {'status': 'PASSED', 'mode': 'development_only' if development_only else 'complete_delivery',
              'actual_attempts_in_ledger': len(attempts), 'remaining_execution_budget': 192-len(attempts),
              'model_calls_registered': 0,
              'inputs': {s: {k: v for k, v in d.items() if k not in ('units', 'queries')} for s, d in inputs.items()},
              'checker_imports_core': False, 'checker_new_sandbox_executions': 0}
    if development_only:
        result['heldout_files_read'] = False
        return result
    require(len(counts) == 48 and len({a['family_id'] for a in attempts}) == 12, 'Expected 48 unique units/12 families')
    require(all(sum(a['split'] == s for a in attempts) == 24 for s in splits), 'Each split must have 24 attempts in this completed run')
    original_plan = frozen(out/'PLAN.json')
    plan = frozen(out/'FINAL_PLAN.json')
    require(plan['parent_plan_sha256'] == digest((out/'PLAN.json').read_bytes()), 'Amended plan lost original parent binding')
    require(plan['spec_hashes'] == registration['spec_hashes'], 'Amended plan changed unit definitions')
    require(plan['budgets'] == original_plan['budgets'] and plan['quotes'] == original_plan['quotes'], 'Amendment silently changed cost budgets')
    for relative, expected in plan['code_hashes'].items():
        require(digest(confined(REPO, relative).read_bytes()) == expected, 'Frozen core code changed: ' + relative)
    for attempt in attempts:
        if attempt['split'] == 'heldout':
            require(timestamp(attempt['at']) >= timestamp(plan['frozen_at']), 'Heldout ran before final freeze')
            require(attempt['plan_sha'] == digest((out/'FINAL_PLAN.json').read_bytes()), 'Heldout attempt uses different plan')
    # This guard deliberately occurs before opening any oracle or Full file.
    seals = {s: read_json(out/f'{s}_TRAJECTORY_SEAL.json') for s in splits}
    access = read_lines(out/'ACCESS_LOG.jsonl')
    joins = [r for r in access if r['action'] == 'reference_join_heldout']
    require(len(joins) == 1, 'Heldout oracle join must occur exactly once')
    require(all(timestamp(seal['sealed_at']) <= timestamp(joins[0]['at']) for seal in seals.values()), 'Oracle joined before both trajectory seals')
    require(all(seal['oracle_joined'] is False for seal in seals.values()), 'Trajectory seal already depended on oracle')
    result['replays'] = {}
    for split in splits:
        oracle = read_json(out/'oracle'/f'{split}.json')
        require(set(oracle) == set(inputs[split]['queries']), 'Oracle query universe differs')
        result['replays'][split] = audit_trajectories(out, split, plan, inputs[split]['queries'], oracle)
    summary_path = out/'SUMMARY.json'
    if summary_path.exists():
        summary = read_json(summary_path)
        require(summary['sandbox_executions'] == len(attempts) and summary['logical_units'] == 48 and summary['families'] == 12, 'Summary sample counts disagree')
        require(summary['heldout_wrong_point_repeated_rows'] == result['replays']['heldout']['wrong_point_rows'], 'Summary wrong-point count disagrees')
        require(summary['heldout_wrong_safe_repeated_rows'] == result['replays']['heldout']['wrong_safe_rows'], 'Summary wrong-safe count disagrees')
        areas = result['replays']['heldout']['family_equal_correct_coverage_auc']
        for label, treatment, baseline in [('static_vs_global', 'metric_static', 'global_fixed'), ('dynamic_vs_static', 'dependency_guided', 'metric_static')]:
            require(abs(summary[label]['auc_difference'] - (areas[treatment]-areas[baseline])) < 1e-12, 'Summary AUC difference disagrees: ' + label)
        curve_count = 0
        with (out/'AGGREGATE_CURVES.csv').open(encoding='utf-8-sig', newline='') as stream:
            published = {(r['split'], r['policy'], int(r['budget'])): r for r in csv.DictReader(stream)
                         if r['mechanism'] == 'ALL' and r['metric'] == 'ALL'}
        for split in splits:
            for curve in result['replays'][split]['family_equal_curves']:
                row = published[(split, curve['policy'], curve['budget'])]
                for independent_key, reported_key in [('correct_coverage','family_equal_correct_point_coverage'),
                                                      ('wrong_point_rate','family_equal_wrong_point_rate'),
                                                      ('selective_error_rate','family_equal_selective_error_rate')]:
                    if curve[independent_key] is None:
                        require(row[reported_key] == '', 'Reported undefined rate was converted to a number')
                    else:
                        require(abs(curve[independent_key]-float(row[reported_key])) < 1e-12,
                                'Published family-equal curve disagrees: ' + str((split, curve['policy'], curve['budget'], reported_key)))
                curve_count += 1
        result['aggregate_curve_rows_independently_compared'] = curve_count
        result['summary_independently_recomputed'] = True
    else:
        result['summary_independently_recomputed'] = 'NOT_YET_CREATED'
    result['oracle_join_after_both_trajectory_seals'] = True
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('run_directory', type=Path)
    parser.add_argument('--development-only', action='store_true')
    args = parser.parse_args()
    try:
        output = verify(args.run_directory.resolve(), args.development_only)
    except Exception as error:
        print(json.dumps({'status': 'FAILED', 'error_type': type(error).__name__, 'message': str(error)}, ensure_ascii=True))
        sys.exit(1)
    print(json.dumps(output, ensure_ascii=True, sort_keys=True, indent=2))