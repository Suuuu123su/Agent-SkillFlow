#!/usr/bin/env python3
"""Frozen-plan, offline, query-local P4 evidence recovery pilot (stdlib only).

prepare writes PLAN.json before evaluating any predictor. run verifies that plan,
uses archived P4 code, and separates policy inputs from evaluation-only labels.
No business action, model, socket, or paid service is invoked.
"""
import argparse
import collections
import csv
import hashlib
import io
import json
import random
import re
import statistics
import sys
import time
import types
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P4 = ROOT / '论文材料/P4_测量证据消融/p4-20260917-123623'
ARCHIVE = P4 / 'p4-evidence-ablation-review.zip'
DEFAULT_OUT = ROOT / '论文材料/修复与补强_20260919/evidence_pilot'
FAMILIES = ['receipt', 'grant', 'provenance', 'counterfactual',
            'task_success_evidence', 'lifecycle', 'scope_lifetime',
            'decision_reason', 'failure']
METRICS = ['UEA', 'ALR', 'RIR', 'TaskSuccess', 'CI']
SEEDS = [19101, 19102, 19103, 19104, 19105, 19106, 19107, 19108]
PRIORITY = {
    'UEA': ['receipt', 'grant', 'scope_lifetime', 'lifecycle'],
    'ALR': ['provenance', 'grant', 'decision_reason', 'receipt',
            'counterfactual', 'lifecycle', 'scope_lifetime'],
    'RIR': ['lifecycle', 'receipt', 'grant', 'scope_lifetime',
            'provenance', 'counterfactual', 'failure', 'task_success_evidence'],
    'TaskSuccess': ['lifecycle', 'receipt', 'task_success_evidence'],
    'CI': ['counterfactual', 'provenance', 'receipt'],
}
MEMBERS = ['minimal_data/BASE_DOCUMENTS.jsonl',
           'minimal_data/PREDICTOR_QUERIES.jsonl', 'QUERY_REGISTRY.jsonl',
           'GOLD_PROVENANCE.jsonl', 'control/UNIT_MAP.json',
           'code/predictor.py', 'code/views.py', 'code/independent_reference.py']


def canonical(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_rows(data):
    return [json.loads(line) for line in data.decode('utf-8-sig').splitlines() if line]


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def save_csv(path, rows):
    rows = list(rows)
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: canonical(v) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def archive_data():
    with zipfile.ZipFile(ARCHIVE) as z:
        return {name: z.read(name) for name in MEMBERS}


def sample_queries(queries, registry, limit=240):
    """Round-robin metric x domain strata; <=1 query per registry unit group.

    Group uniqueness is NOT a claim that runs/templates/branches are independent.
    Neither predictor outputs nor reference labels enter selection.
    """
    pools = collections.defaultdict(list)
    for q in queries:
        if q['metric'] in METRICS:
            pools[(q['metric'], registry[q['query_id']]['domain'])].append(q)
    for pool in pools.values():
        pool.sort(key=lambda q: digest(('pilot-v1|' + q['query_id']).encode()))
    selected, used = [], set()
    strata = sorted(pools)
    while len(selected) < limit:
        added = False
        for s in strata:
            while pools[s]:
                q = pools[s].pop(0)
                unit_group = registry[q['query_id']]['independence_group']
                if unit_group not in used:
                    used.add(unit_group)
                    selected.append(q)
                    added = True
                    break
            if len(selected) >= limit:
                break
        if not added:
            break
    return selected


def prepare(out):
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'PLAN.json').exists():
        raise SystemExit('PLAN.json already exists; use run or a fresh --out directory.')
    data = archive_data()
    queries = json_rows(data['minimal_data/PREDICTOR_QUERIES.jsonl'])
    reg = {r['query_id']: r for r in json_rows(data['QUERY_REGISTRY.jsonl'])}
    selected = sample_queries(queries, reg)
    plan = {
        'version': 'evidence-recovery-pilot-v1',
        'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'status': 'FROZEN_BEFORE_PREDICTION',
        'archive_relative_path': str(ARCHIVE.relative_to(ROOT)),
        'archive_sha256': digest(ARCHIVE.read_bytes()),
        'member_sha256': {k: digest(v) for k, v in data.items()},
        'runner_sha256': digest(Path(__file__).read_bytes()),
        'selection_rule': 'metric/domain round robin, stable sha256 ranking, at most one query per registry independence_group; no outcome conditioning',
        'selected_query_ids': [q['query_id'] for q in selected],
        'query_count': len(selected), 'maximum_query_count': 240,
        'metrics': METRICS, 'families': FAMILIES, 'random_seeds': SEEDS,
        'global_fixed_order': FAMILIES, 'metric_fixed_priorities': PRIORITY,
        'conditions': {
            'all_nine_missing': {'initial_visible_families': 0},
            'five_missing': {'initial_visible_families': 4,
                             'selection': 'sha256(pilot-mask-v1|query_id|family), first four visible'},
        },
        'budget': list(range(len(FAMILIES) + 1)),
        'unit_cost': 'one family restored throughout this query document including nested branch documents; no sharing across queries',
        'secondary_cost': 'nonnegative change in canonical serialized projected-document UTF-8 byte length; proxy only, excludes transport/logging/runtime',
        'stop_rule': 'point or not_applicable; all policies stop identically and repeat terminal state at remaining budgets',
        'guided_inputs': ['metric', 'protocol', 'current visible prediction status',
                          'current visible missing_evidence', 'acquired family names'],
        'guided_rule': 'first missing not-yet-acquired family in frozen metric-specific order; fallback same order',
        'policy_forbidden_inputs': ['Full predictions', 'reference labels',
                                    'hidden documents', 'other query outcomes'],
        'projection': 'compose archived P4 views.project in FAMILIES order on a fresh base; preserves all P4 cross-field cleanup',
        'outcome_rules': 'keep Full unknown/not_applicable and all errors; do not select Full-point cases',
        'reported_measures': ['point coverage', 'eligibility coverage', 'unknown rate',
                              'agreement with Full (not truth)', 'Full state agreement',
                              'independent point-reference selective accuracy and coverage',
                              'independent eligibility agreement', 'unit-family costs', 'byte proxy'],
        'statistical_unit': '240 distinct registry units, not proven independent tasks; budgets/policies/seeds repeated measurements; template/family dependence explicit; descriptive results only',
        'scope_limits': ['offline saved observations', 'no natural-language ground truth',
                         'no new causal CI evidence', 'no actual online collection cost',
                         'no HIAA queries', 'no Provenance/failure self-output queries',
                         'no globally minimal-evidence claim', 'no new three-valued logic claim'],
        'execution': {'network_calls': 0, 'model_calls': 0, 'business_tool_calls': 0},
    }
    save_json(out / 'PLAN.json', plan)
    (out / 'PLAN.sha256').write_text(digest((out / 'PLAN.json').read_bytes()) + '\n', encoding='ascii')
    print(json.dumps({'plan_written': str(out / 'PLAN.json'), 'queries': len(selected)}))


def load_module(name, code):
    module = types.ModuleType(name)
    exec(compile(code, '<archived-' + name + '>', 'exec'), module.__dict__)
    return module


def family_order(metric):
    primary = PRIORITY[metric]
    return primary + [f for f in FAMILIES if f not in primary]


def choose_family(policy, metric, protocol, prediction, acquired, order):
    """Acquisition policy has no document, Full, reference, or registry argument."""
    remaining = [f for f in order if f not in acquired]
    if not remaining:
        return None
    if policy == 'contract_guided':
        missing = {x.split('#/', 1)[-1].split('/', 1)[0] for x in prediction['missing_evidence']}
        needed = [f for f in remaining if f in missing]
        if needed:
            return needed[0]
    return remaining[0]


def visible_initial(qid, condition):
    if condition == 'all_nine_missing':
        return set()
    return set(sorted(FAMILIES, key=lambda f: digest(('pilot-mask-v1|' + qid + '|' + f).encode()))[:4])


def cluster_label(reg):
    """Only explicit construct branch families can be recovered with certainty."""
    if reg['domain'] == 'CONTROLLED_CONSTRUCT':
        return 'construct:' + re.sub(r'-(prefix|original|identity|neutral)$', '', reg['native_unit_ref'])
    return 'source-block:' + reg['source_ref'].split('#')[0]


def safe_rate(a, b):
    return a / b if b else None


def summary(rows):
    n = len(rows)
    ref_available = sum(r['reference_truth_available'] for r in rows)
    ref_answered = sum(r['reference_truth_available'] and r['status'] == 'point' for r in rows)
    ref_correct = sum(r['reference_point_correct'] is True for r in rows)
    ref_elig_known = sum(r['reference_eligibility_known'] for r in rows)
    ref_elig_answered = sum(r['reference_eligibility_known'] and r['eligibility'] is not None for r in rows)
    ref_elig_correct = sum(r['reference_eligibility_correct'] is True for r in rows)
    full_pair = sum(r['full_point_comparable'] for r in rows)
    points = sum(r['status'] == 'point' for r in rows)
    return {
        'n_query_observations': n,
        'unique_queries': len({r['query_id'] for r in rows}),
        'unique_registry_units': len({r['unit'] for r in rows}),
        'explicit_construct_families': len({r['source_cluster'] for r in rows if r['domain'] == 'CONTROLLED_CONSTRUCT'}),
        'point_count': points, 'point_coverage': safe_rate(points, n),
        'not_applicable_count': sum(r['status'] == 'not_applicable' for r in rows),
        'eligibility_coverage': safe_rate(sum(r['eligibility'] is not None for r in rows), n),
        'unknown_count': sum(r['status'] in ['unknown', 'bounded'] for r in rows),
        'unknown_rate': safe_rate(sum(r['status'] in ['unknown', 'bounded'] for r in rows), n),
        'analysis_errors': sum(r['status'] == 'analysis_error' for r in rows),
        'full_point_pairs': full_pair,
        'full_point_agreement': safe_rate(sum(r['full_point_equal'] is True for r in rows), full_pair),
        'full_state_agreement': safe_rate(sum(r['full_state_equal'] for r in rows), n),
        'point_not_supported_by_full': sum(r['status'] == 'point' and not r['full_point_equal'] for r in rows),
        'independent_truth_n': ref_available, 'independent_answered_n': ref_answered,
        'independent_correct_n': ref_correct,
        'independent_truth_coverage': safe_rate(ref_answered, ref_available),
        'independent_selective_accuracy': safe_rate(ref_correct, ref_answered),
        'independent_eligibility_n': ref_elig_known,
        'independent_eligibility_coverage': safe_rate(ref_elig_answered, ref_elig_known),
        'independent_eligibility_accuracy': safe_rate(ref_elig_correct, ref_elig_answered),
        'mean_acquired_families': statistics.mean(r['acquired_cost'] for r in rows),
        'mean_added_json_bytes': statistics.mean(r['added_json_bytes'] for r in rows),
    }


def run(out):
    plan_bytes = (out / 'PLAN.json').read_bytes()
    plan = json.loads(plan_bytes)
    assert digest(plan_bytes) == (out / 'PLAN.sha256').read_text().strip(), 'Plan changed'
    assert digest(Path(__file__).read_bytes()) == plan['runner_sha256'], 'Runner changed after freeze'
    assert digest(ARCHIVE.read_bytes()) == plan['archive_sha256'], 'Archive changed'
    data = archive_data()
    assert {k: digest(v) for k, v in data.items()} == plan['member_sha256']
    predictor = load_module('predictor', data['code/predictor.py'])
    views = load_module('views', data['code/views.py'])
    queries = {q['query_id']: q for q in json_rows(data['minimal_data/PREDICTOR_QUERIES.jsonl'])}
    registry = {r['query_id']: r for r in json_rows(data['QUERY_REGISTRY.jsonl'])}
    documents = {d['id']: d for d in json_rows(data['minimal_data/BASE_DOCUMENTS.jsonl'])}
    selected = [queries[qid] for qid in plan['selected_query_ids']]
    assert len(selected) <= 240
    profiles = {family: profile for profile, family in views.PROFILES.items() if family}
    raw_rows, errors, cache, sizes = [], [], {}, {}
    started = time.time()
    denied = []

    def offline_guard(event, args):
        if event.startswith(('socket.', 'subprocess.', 'os.system')):
            denied.append(event)
            raise RuntimeError('OFFLINE_PILOT_FORBIDS_NETWORK_SUBPROCESS_BUSINESS_EXECUTION')
    sys.addaudithook(offline_guard)

    def predict(q, visible):
        key = q['query_id'], tuple(sorted(visible))
        if key in cache:
            return cache[key], sizes[key]
        d = documents[q['unit']]
        # Fresh projected tree each time; no mutation or sharing between trajectories.
        d = json.loads(canonical(d))
        for family in FAMILIES:
            if family not in visible:
                d = views.project(d, profiles[family])
        size = len(canonical(d).encode('utf-8'))
        a = predictor.Analyzer({q['unit']: d})
        try:
            pred = a.run(q)
        except Exception as exc:
            pred = {'status': 'analysis_error', 'eligibility': None, 'value': None,
                    'lower': None, 'upper': None,
                    'missing_evidence': sorted(getattr(a, 'missing', [])),
                    'reason': type(exc).__name__ + ': ' + str(exc)}
            errors.append({'query_id': q['query_id'], 'visible_families': sorted(visible),
                           'error': pred['reason']})
        cache[key], sizes[key] = pred, size
        return pred, size

    # Policy trajectories are completed before reference labels or Full are read.
    for q in selected:
        reg = registry[q['query_id']]
        for condition in plan['conditions']:
            initial = visible_initial(q['query_id'], condition)
            policies = [('global_fixed', 0), ('metric_fixed', 0), ('contract_guided', 0)]
            policies += [('random', seed) for seed in SEEDS]
            for policy, seed in policies:
                visible = set(initial)
                order = FAMILIES.copy() if policy in ['global_fixed', 'random'] else family_order(q['metric'])
                if policy == 'random':
                    random.Random(str(seed) + '|' + q['query_id']).shuffle(order)
                pred, initial_size = predict(q, visible)
                added_bytes, cost, choices = 0, 0, []
                for budget in plan['budget']:
                    if budget:
                        chosen = None if pred['status'] in ['point', 'not_applicable'] else choose_family(policy, q['metric'], q['protocol'], pred, visible, order)
                        if chosen:
                            _, before_size = predict(q, visible)
                            visible.add(chosen)
                            pred, after_size = predict(q, visible)
                            cost += 1
                            added_bytes += max(0, after_size - before_size)
                            choices.append(chosen)
                    raw_rows.append({
                        'query_id': q['query_id'], 'unit': q['unit'], 'domain': reg['domain'],
                        'metric': q['metric'], 'protocol': q['protocol'],
                        'registry_group': reg['independence_group'], 'source_cluster': cluster_label(reg),
                        'condition': condition, 'policy': policy, 'seed': seed, 'budget': budget,
                        'acquired_cost': cost, 'added_json_bytes': added_bytes,
                        'initial_json_bytes': initial_size, 'acquired_order': choices.copy(),
                        'initial_families': sorted(initial), 'visible_families': sorted(visible),
                        'status': pred['status'], 'eligibility': pred['eligibility'],
                        'value': pred['value'], 'lower': pred.get('lower'), 'upper': pred.get('upper'),
                        'missing_evidence': pred['missing_evidence'], 'reason': pred.get('reason'),
                    })
    # EVALUATION PLANE. Policy selection has finished; Full and independent reference
    # cannot affect query inclusion, acquisition order, or stopping decisions above.
    gold = {r['query_id']: r for r in json_rows(data['GOLD_PROVENANCE.jsonl'])}
    full = {q['query_id']: predict(q, set(FAMILIES))[0] for q in selected}
    for r in raw_rows:
        f, g = full[r['query_id']], gold.get(r['query_id'], {})
        same_point = r['status'] == 'point' and f['status'] == 'point'
        truth = bool(g.get('truth_available'))
        ref_elig = bool(g.get('eligibility_known'))
        r.update({
            'full_status': f['status'], 'full_eligibility': f['eligibility'], 'full_value': f['value'],
            'full_point_comparable': same_point,
            'full_point_equal': r['value'] == f['value'] if same_point else None,
            'full_state_equal': all(r[k] == f[k] for k in ['status', 'eligibility', 'value']),
            'reference_present': bool(g), 'reference_truth_available': truth,
            'reference_eligibility_known': ref_elig,
            'reference_value': g.get('value') if truth else None,
            'reference_eligibility': g.get('eligibility') if ref_elig else None,
            'reference_point_correct': r['value'] == g['value'] if truth and r['status'] == 'point' else None,
            'reference_eligibility_correct': r['eligibility'] == g['eligibility'] if ref_elig and r['eligibility'] is not None else None,
        })
    # Full is a comparator once per query, not one extra independent task per mask.
    full_rows = []
    for q in selected:
        source = next(r for r in raw_rows if r['query_id'] == q['query_id'])
        f, g = full[q['query_id']], gold.get(q['query_id'], {})
        row = dict(source)
        row.update(condition='Full', policy='Full', seed=0, budget=9,
                   acquired_cost=9, added_json_bytes=0, acquired_order=FAMILIES.copy(),
                   initial_families=[], visible_families=FAMILIES.copy(),
                   status=f['status'], eligibility=f['eligibility'], value=f['value'],
                   lower=f.get('lower'), upper=f.get('upper'), reason=f.get('reason'),
                   missing_evidence=f['missing_evidence'], full_state_equal=True,
                   full_point_comparable=f['status'] == 'point',
                   full_point_equal=True if f['status'] == 'point' else None,
                   reference_point_correct=f['value'] == g.get('value') if g.get('truth_available') and f['status'] == 'point' else None,
                   reference_eligibility_correct=f['eligibility'] == g.get('eligibility') if g.get('eligibility_known') and f['eligibility'] is not None else None)
        full_rows.append(row)
    all_rows = raw_rows + full_rows
    save_csv(out / 'query_results.csv', all_rows)
    dimensions = ['condition', 'policy', 'seed', 'budget']
    buckets = collections.defaultdict(list)
    for r in all_rows:
        buckets[tuple(r[k] for k in dimensions)].append(r)
    summaries = [dict(zip(dimensions, key)) | summary(rs) for key, rs in sorted(buckets.items())]
    save_csv(out / 'summary.csv', summaries)
    fine_dims = dimensions + ['metric', 'domain']
    fine = collections.defaultdict(list)
    for r in all_rows:
        fine[tuple(r[k] for k in fine_dims)].append(r)
    save_csv(out / 'by_metric_domain.csv', [dict(zip(fine_dims, key)) | summary(rs) for key, rs in sorted(fine.items())])
    sampling = [{'query_id': q['query_id'], 'unit': q['unit'], 'metric': q['metric'],
                 'protocol': q['protocol'], **{k: registry[q['query_id']][k] for k in ['domain', 'independence_group', 'source_ref', 'native_unit_ref']},
                 'source_cluster': cluster_label(registry[q['query_id']])} for q in selected]
    save_csv(out / 'sample.csv', sampling)
    save_json(out / 'analysis_errors.json', errors)
    save_json(out / 'RUN_STATUS.json', {
        'status': 'COMPLETED_WITH_ERRORS' if errors else 'COMPLETED',
        'plan_sha256': digest(plan_bytes), 'archive_sha256': plan['archive_sha256'],
        'unique_queries': len(selected), 'unique_registry_units': len({q['unit'] for q in selected}),
        'unique_construct_families': len({x['source_cluster'] for x in sampling if x['domain'] == 'CONTROLLED_CONSTRUCT'}),
        'rows_including_full': len(all_rows), 'distinct_cached_query_masks': len(cache),
        'errors': len(errors), 'network_calls': 0, 'model_calls': 0, 'business_tool_calls': 0,
        'blocked_operations': denied, 'duration_seconds': round(time.time() - started, 3),
        'independent_reference_queries': sum(q['query_id'] in gold for q in selected),
        'full_summary': summary(full_rows),
        'source_code': 'archived predictor/views; no predictor semantics patched',
        'warning': 'registry unit uniqueness does not imply statistical independence; repeated budgets/policies/random seeds never counted as extra tasks',
    })
    print(json.dumps({'queries': len(selected), 'errors': len(errors), 'rows': len(all_rows), 'seconds': round(time.time() - started, 2)}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    (prepare if args.action == 'prepare' else run)(args.out.resolve())


if __name__ == '__main__':
    main()
