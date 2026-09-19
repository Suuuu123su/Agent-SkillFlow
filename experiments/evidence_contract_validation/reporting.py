"""Post-seal, family-aware reporting for the frozen offline recovery study.

This module runs no sandbox, model, network request, or policy optimization.
Reference and Full files are opened only after both prediction seals verify.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import gzip
from html import escape
import json
import os
from pathlib import Path
import statistics
import sys

from .common import canonical, now, read_json, read_rows, sha, write_csv, write_json

SPLITS = ('development', 'heldout')
COUNTERS = ('observations', 'oracle_point', 'oracle_unknown', 'oracle_not_applicable',
            'point', 'bounded', 'unknown', 'not_applicable', 'error', 'infeasible',
            'answered_oracle_point', 'correct_point', 'wrong_point', 'wrong_safe',
            'full_comparable', 'full_agree', 'full_point_comparable',
            'full_point_agree', 'feasible', 'charged_total_bytes', 'initial_bytes',
            'visible_json_bytes', 'acquired_channels', 'evidence_fields', 'evidence_events')
RATE_DEFINITIONS = {
    'correct_point_coverage': ('correct_point', 'oracle_point'),
    'wrong_point_rate': ('wrong_point', 'oracle_point'),
    'selective_error_rate': ('wrong_point', 'answered_oracle_point'),
    'wrong_safe_rate': ('wrong_safe', 'oracle_point'),
    'point_coverage': ('point', 'observations'),
    'unknown_rate': ('unknown', 'observations'),
    'bounded_rate': ('bounded', 'observations'),
    'not_applicable_rate': ('not_applicable', 'observations'),
    'error_rate': ('error', 'observations'),
    'infeasible_rate': ('infeasible', 'observations'),
    'reference_coverage': ('oracle_point', 'observations'),
    'reference_unknown_rate': ('oracle_unknown', 'observations'),
    'reference_not_applicable_rate': ('oracle_not_applicable', 'observations'),
    'full_state_agreement': ('full_agree', 'full_comparable'),
    'full_point_agreement': ('full_point_agree', 'full_point_comparable'),
    'mean_charged_bytes_feasible': ('charged_total_bytes', 'feasible'),
    'mean_initial_bytes': ('initial_bytes', 'observations'),
    'mean_visible_json_bytes': ('visible_json_bytes', 'observations'),
    'mean_acquired_channels': ('acquired_channels', 'observations'),
    'mean_evidence_fields': ('evidence_fields', 'observations'),
    'mean_evidence_events': ('evidence_events', 'observations'),
}


def _ratio(a, b):
    return a / b if b else None


def _mean(values):
    values = [value for value in values if value is not None]
    return statistics.mean(values) if values else None


def _percentage(value):
    return 'N/A' if value is None else f'{100 * value:.2f}%'


def _number(value):
    return 'N/A' if value is None else f'{value:.5f}'


def _policy(name):
    return 'random' if name.startswith('random_') else name


def _measure(prediction, oracle, full, metric):
    status = prediction['status']
    oracle_point = oracle['status'] == 'point'
    answered = oracle_point and status == 'point'
    correct = answered and prediction['value'] == oracle['value']
    wrong = answered and not correct
    full_pair = status == 'point' and full['status'] == 'point'
    result = {key: 0.0 for key in COUNTERS}
    result.update(observations=1.0, oracle_point=float(oracle_point),
                  oracle_unknown=float(oracle['status'] in ('unknown', 'bounded', 'error', 'analysis_error')),
                  oracle_not_applicable=float(oracle['status'] == 'not_applicable'),
                  point=float(status == 'point'), bounded=float(status == 'bounded'),
                  unknown=float(status == 'unknown'), not_applicable=float(status == 'not_applicable'),
                  error=float(status in ('error', 'analysis_error')), infeasible=float(status == 'infeasible'),
                  answered_oracle_point=float(answered), correct_point=float(correct),
                  wrong_point=float(wrong),
                  wrong_safe=float(wrong and metric == 'UEA' and prediction['value'] in (0, False)),
                  full_comparable=1.0,
                  full_agree=float(status == full['status'] and prediction.get('value') == full.get('value')),
                  full_point_comparable=float(full_pair),
                  full_point_agree=float(full_pair and prediction['value'] == full['value']),
                  feasible=float(status != 'infeasible'))
    for key in ('charged_total_bytes', 'initial_bytes', 'visible_json_bytes',
                'acquired_channels', 'evidence_fields', 'evidence_events'):
        result[key] = float(prediction.get(key, 0))
    return result


def _sum(records):
    return {key: sum(row[key] for row in records) for key in COUNTERS}


def _rates(counts):
    return {key: _ratio(counts[a], counts[b]) for key, (a, b) in RATE_DEFINITIONS.items()}


def _collapse_repeats(rows):
    """Average policy-order and mask seeds within query/condition/budget first."""
    groups = defaultdict(list)
    for row in rows:
        key = tuple(row[k] for k in ('split', 'query_id', 'unit', 'family_id', 'metric',
                                     'mechanism', 'condition', 'policy_family', 'budget'))
        groups[key].append(row)
    result = []
    keys = ('split', 'query_id', 'unit', 'family_id', 'metric', 'mechanism',
            'condition', 'policy', 'budget')
    for key, members in sorted(groups.items()):
        counts = {name: statistics.mean(row[name] for row in members) for name in COUNTERS}
        result.append(dict(zip(keys, key), **counts, seed_repetitions=len(members)))
    return result


def _family_tables(collapsed):
    groups = defaultdict(list)
    for row in collapsed:
        for mechanism in (row['mechanism'], 'ALL'):
            for metric in (row['metric'], 'ALL'):
                key = (row['split'], row['family_id'], mechanism, metric, row['policy'], row['budget'])
                groups[key].append(row)
    result = []
    names = ('split', 'family_id', 'mechanism', 'metric', 'policy', 'budget')
    for key, records in sorted(groups.items()):
        counts = _sum(records)
        result.append(dict(zip(names, key), **counts, **_rates(counts),
                           query_count=len({r['query_id'] for r in records}),
                           unit_count=len({r['unit'] for r in records}),
                           averaged_query_conditions=len(records)))
    return result


def _aggregate(family_rows):
    groups = defaultdict(list)
    for row in family_rows:
        key = tuple(row[k] for k in ('split', 'mechanism', 'metric', 'policy', 'budget'))
        groups[key].append(row)
    result = []
    for key, members in sorted(groups.items()):
        counts = _sum(members)
        pooled = {'pooled_' + k: v for k, v in _rates(counts).items()}
        equal = {'family_equal_' + k: _mean([row[k] for row in members]) for k in RATE_DEFINITIONS}
        result.append(dict(zip(('split', 'mechanism', 'metric', 'policy', 'budget'), key),
                           **counts, **pooled, **equal, families=len(members),
                           families_with_point_reference=sum(row['oracle_point'] > 0 for row in members)))
    return result


def _auc(points, x_key, y_key, budgets):
    """Normalized trapezoidal area on the exact common frozen byte interval."""
    by_x = {p[x_key]: p[y_key] for p in points}
    if any(b not in by_x or by_x[b] is None for b in budgets):
        return None
    span = budgets[-1] - budgets[0]
    if span <= 0:
        return None
    return sum((b - a) * (by_x[a] + by_x[b]) / 2 for a, b in zip(budgets, budgets[1:])) / span


def _full_summary(registry, truth, full, split):
    groups = defaultdict(list)
    for q in registry:
        qid = q['query_id']
        row = _measure(full[qid], truth[qid], full[qid], q['metric'])
        row.update(family_id=q['family_id'])
        groups[q['metric']].append(row)
        groups['ALL'].append(row)
    output = []
    for metric, rows in sorted(groups.items()):
        counts = _sum(rows)
        per_family = defaultdict(list)
        for row in rows:
            per_family[row['family_id']].append(row)
        family_rates = [_rates(_sum(group)) for group in per_family.values()]
        output.append({'split': split, 'metric': metric, 'queries': len(rows),
                       'families': len(per_family), **counts, **_rates(counts),
                       'family_equal_correct_point_coverage': _mean([x['correct_point_coverage'] for x in family_rates]),
                       'family_equal_wrong_point_rate': _mean([x['wrong_point_rate'] for x in family_rates]),
                       'role': 'complete observation comparator; not a free acquisition policy'})
    return output


def _compare(curves, families, budgets, treatment, baseline):
    selected = [row for row in curves if row['split'] == 'heldout' and
                row['mechanism'] == 'ALL' and row['metric'] == 'ALL']
    by_policy = defaultdict(list)
    for row in selected:
        by_policy[row['policy']].append(row)
    if treatment not in by_policy or baseline not in by_policy:
        return {'status': 'NOT_RUN', 'treatment': treatment, 'baseline': baseline}
    treatment_auc = _auc(by_policy[treatment], 'budget', 'family_equal_correct_point_coverage', budgets)
    baseline_auc = _auc(by_policy[baseline], 'budget', 'family_equal_correct_point_coverage', budgets)
    delta = None if treatment_auc is None or baseline_auc is None else treatment_auc - baseline_auc
    a = {r['budget']: r for r in by_policy[treatment]}
    b = {r['budget']: r for r in by_policy[baseline]}
    differences = []
    for budget in budgets:
        left, right = a[budget], b[budget]
        differences.append({'budget': budget,
                            'correct_coverage_difference': left['family_equal_correct_point_coverage'] - right['family_equal_correct_point_coverage'],
                            'wrong_rate_difference': left['family_equal_wrong_point_rate'] - right['family_equal_wrong_point_rate']})
    wrong_not_increased = all(row['wrong_rate_difference'] <= 1e-12 for row in differences)
    paired = []
    family_ids = sorted({r['family_id'] for r in families if r['split'] == 'heldout'})
    for family in family_ids:
        rr = [r for r in families if r['split'] == 'heldout' and r['family_id'] == family
              and r['mechanism'] == 'ALL' and r['metric'] == 'ALL']
        aa = _auc([r for r in rr if r['policy'] == treatment], 'budget', 'correct_point_coverage', budgets)
        bb = _auc([r for r in rr if r['policy'] == baseline], 'budget', 'correct_point_coverage', budgets)
        paired.append({'family_id': family, 'treatment_auc': aa, 'baseline_auc': bb,
                       'difference': None if aa is None or bb is None else aa - bb})
    positive = sum(r['difference'] is not None and r['difference'] > 1e-12 for r in paired)
    supported = delta is not None and delta > 1e-12 and wrong_not_increased
    if treatment == 'dependency_guided':
        supported = supported and positive >= 2
    return {'status': 'SUPPORTED_IN_SCOPE' if supported else 'UNSUPPORTED',
            'treatment': treatment, 'baseline': baseline, 'correct_coverage_auc': treatment_auc,
            'baseline_correct_coverage_auc': baseline_auc, 'auc_difference': delta,
            'wrong_point_rate_not_increased_at_any_budget': wrong_not_increased,
            'budgets': differences, 'paired_families': paired,
            'positive_families': positive, 'negative_families': sum(r['difference'] is not None and r['difference'] < -1e-12 for r in paired),
            'statistical_status': 'descriptive; six heldout families, no iid-query CI or significance test'}


def _cases(out):
    cases, type_counts = [], Counter()
    # Restricted to files named record.json beneath this experiment output root.
    for path in sorted(out.rglob('record.json')):
        if 'policy_ipc' in path.parts:
            continue
        record = read_json(path)
        if record.get('schema_version') != 'independent-sandbox-raw-v1':
            continue
        supervisor = record['supervisor']
        collector = record['collector']
        changes = supervisor['side_effect_records']
        label = None
        if changes and collector['receipt'] is None:
            label = 'actual_persistent_effect_without_collector_ack'
        elif not changes:
            label = 'attempt_without_persistent_effect'
        binding = record['task_requirements']['binding']
        wanted_path = record['task_requirements']['binding_path']
        actual = supervisor['state_after'].get(wanted_path)
        if actual:
            import base64
            actual_binding = json.loads(base64.b64decode(actual['content_base64']))
            if actual_binding != binding:
                label = 'actual_artifact_with_wrong_task_binding'
        if label:
            type_counts[label] += 1
            cases.append({'execution_unit_id': record['execution_unit_id'],
                          'family_id': record['family_id'], 'split': record['split'],
                          'case_type': label, 'record_path': path.relative_to(out).as_posix(),
                          'record_sha256': sha(path.read_bytes()),
                          'monitor_complete': supervisor['complete'],
                          'persistent_change_count': len(changes),
                          'collector_ack_present': collector['receipt'] is not None,
                          'process_returncode': supervisor['process_returncode']})
    return cases, dict(type_counts)


def _svg_fallback(path, curves, budgets):
    """Standalone SVG fallback; no plotting package exists in the frozen venv."""
    colors = {'global_fixed': '#777777', 'random': '#9970ab',
              'metric_static': '#2166ac', 'dependency_guided': '#d6604d'}
    chosen = [r for r in curves if r['split'] == 'heldout' and r['metric'] == 'ALL' and r['mechanism'] == 'ALL']
    policies = sorted({r['policy'] for r in chosen})
    width, height = 1080, 470
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<title>Heldout correct coverage and wrong-point rate against frozen total byte budgets</title>',
             '<desc>Family-equal descriptive curves. Policy and missingness seeds averaged inside each query and condition. Infeasible rows remain in common denominators. No confidence intervals.</desc>',
             '<rect width="100%" height="100%" fill="white"/>',
             '<g font-family="Arial,sans-serif" fill="#222" font-size="12">',
             '<text x="40" y="28" font-size="18">Heldout: coverage and error at common total-byte budgets</text>']
    for panel, (field, title) in enumerate([('family_equal_correct_point_coverage', 'Correct definite coverage / available point oracle'),
                                            ('family_equal_wrong_point_rate', 'Wrong definite judgments / available point oracle')]):
        x0, y0, w, h = 75 + panel * 530, 75, 440, 265
        def xy(budget, rate):
            return x0 + (budget - budgets[0]) / max(1, budgets[-1] - budgets[0]) * w, y0 + h * (1 - rate)
        parts.append(f'<text x="{x0}" y="{y0-16}" font-size="13">{escape(title)}</text>')
        for i in range(5):
            rate = i / 4
            y = y0 + h * (1 - rate)
            parts.append(f'<line x1="{x0}" y1="{y}" x2="{x0+w}" y2="{y}" stroke="#dddddd"/><text x="{x0-42}" y="{y+4}">{rate:.0%}</text>')
        for budget in budgets:
            x, _ = xy(budget, 0)
            parts.append(f'<line x1="{x}" y1="{y0+h}" x2="{x}" y2="{y0+h+5}" stroke="#444"/>')
        for budget in (budgets[0], budgets[-1]):
            x, _ = xy(budget, 0)
            parts.append(f'<text text-anchor="middle" x="{x}" y="{y0+h+23}">{budget:,}</text>')
        parts.append(f'<text text-anchor="middle" x="{x0+w/2}" y="{y0+h+44}">Total byte budget (initial + returned padded bundles)</text>')
        for policy in policies:
            points = sorted((r for r in chosen if r['policy'] == policy and r[field] is not None), key=lambda r:r['budget'])
            coords = ' '.join(f'{x:.2f},{y:.2f}' for x, y in [xy(r['budget'], r[field]) for r in points])
            color = colors.get(policy, '#333333')
            parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.2" points="{coords}"/>')
            for row in points:
                x, y = xy(row['budget'], row[field])
                parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="{color}"><title>{escape(policy)}; budget={row["budget"]}; rate={row[field]:.6f}</title></circle>')
    for index, policy in enumerate(policies):
        x = 90 + index * 225
        parts.append(f'<line x1="{x}" y1="415" x2="{x+23}" y2="415" stroke="{colors.get(policy,"#333")}" stroke-width="3"/><text x="{x+29}" y="419">{escape(policy)}</text>')
    parts.append('<text x="40" y="453" font-size="11">Six heldout families; repeated measurements; serialized-load proxy; no external-agent or latency claim.</text></g></svg>')
    path.write_text('\n'.join(parts) + '\n', encoding='utf-8')


def _figure(path, curves, budgets):
    """Use matplotlib; all installed packages and writable configuration stay on E:."""
    target = Path('E:/Skill ＆ Harness/tmp/evidence-strengthening-matplotlib')
    config = path.parent / '.mplconfig'
    config.mkdir(exist_ok=True)
    os.environ['MPLCONFIGDIR'] = str(config)
    command = ('python -B -m pip install --target "E:/Skill ＆ Harness/tmp/evidence-strengthening-matplotlib" '
               '--cache-dir "E:/Skill ＆ Harness/tmp/pip-cache-evidence-strengthening" matplotlib')
    inserted = target.exists() and str(target) not in sys.path
    if inserted:
        sys.path.insert(0, str(target))
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.ticker import PercentFormatter, FuncFormatter
    except ImportError as exc:
        _svg_fallback(path, curves, budgets)
        metadata = {'backend': 'stdlib SVG fallback', 'fallback_reason': str(exc),
                    'install_command': command, 'dependency_target': str(target),
                    'svg': path.name, 'png': None, 'confidence_intervals': False}
        write_json(path.parent / 'PLOT_ENVIRONMENT.json', metadata)
        return metadata
    finally:
        if inserted:
            sys.path.remove(str(target))
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.fonttype': 'none'})
    chosen = [r for r in curves if r['split']=='heldout' and r['metric']=='ALL' and r['mechanism']=='ALL']
    colors = {'global_fixed':'#777777', 'random':'#9970ab',
              'metric_static':'#2166ac', 'dependency_guided':'#d6604d'}
    labels = {'global_fixed':'Global fixed', 'random':'Random order (seed mean)',
              'metric_static':'Metric static', 'dependency_guided':'Dependency guided'}
    policies = sorted({r['policy'] for r in chosen})
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.3))
    for axis, field, title in zip(axes,
            ('family_equal_correct_point_coverage','family_equal_wrong_point_rate'),
            ('Correct definite coverage','Wrong definite judgments')):
        for index, policy in enumerate(policies):
            rows = sorted([r for r in chosen if r['policy']==policy], key=lambda r:r['budget'])
            x = [r['budget'] for r in rows if r[field] is not None]
            y = [r[field] for r in rows if r[field] is not None]
            axis.plot(x, y, color=colors.get(policy,'black'), marker=('o','s','^','D')[index%4],
                      markersize=4.0, linewidth=1.8, label=labels.get(policy,policy),
                      linestyle=('-', '--', '-.', ':')[index%4])
        axis.set(title=title, xlabel='Total serialized-byte budget', ylabel='Fraction of point-oracle queries')
        axis.set_xlim(budgets[0], budgets[-1])
        axis.set_ylim(-0.015, 1.015)
        axis.yaxis.set_major_formatter(PercentFormatter(xmax=1))
        axis.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x/1024:g} KiB'))
        axis.grid(axis='y', color='#dddddd', linewidth=0.7)
    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc='lower center', ncol=2, frameon=False,
               bbox_to_anchor=(0.5, 0.055))
    fig.suptitle('Heldout families: equal-byte coverage and error', fontsize=13)
    fig.text(0.5, 0.012, 'Six families; seeds averaged within query; infeasible rows retained; no IID confidence interval.',
             ha='center', fontsize=8)
    fig.subplots_adjust(left=0.085, right=0.985, top=0.84, bottom=0.30, wspace=0.30)
    fig.savefig(path, format='svg', metadata={'Title':'Heldout evidence recovery under frozen total-byte budgets'})
    png = path.with_suffix('.png')
    fig.savefig(png, dpi=240)
    plt.close(fig)
    metadata = {'backend':'matplotlib', 'version':matplotlib.__version__,
                'install_command':command, 'dependency_target':str(target),
                'configuration_directory':str(config), 'svg':path.name, 'png':png.name,
                'confidence_intervals':False, 'python':sys.version,
                'outputs_sha256':{path.name:sha(path.read_bytes()), png.name:sha(png.read_bytes())}}
    write_json(path.parent / 'PLOT_ENVIRONMENT.json', metadata)
    return metadata


def report(output):
    """Generate all results after a once-only heldout replay, then join references."""
    out = Path(output).resolve()
    plan = read_json(out / ('FINAL_PLAN.json' if (out/'FINAL_PLAN.json').exists() else 'PLAN.json'))
    budgets = sorted(set(plan['budgets']))
    if len(budgets) < 2 or len(budgets) > 10:
        raise ValueError('Report requires 2..10 distinct frozen total-byte thresholds')
    if (out / 'SUMMARY.json').exists():
        raise FileExistsError('Report already exists; do not overwrite finalized results')
    hashes = {name:sha((out/name).read_bytes()) for name in ('PLAN.json','FINAL_PLAN.json') if (out/name).exists()}
    for split in SPLITS:
        path = out / f'{split}_PREDICTIONS.jsonl.gz'
        seal = read_json(out / f'{split}_TRAJECTORY_SEAL.json')
        if sha(path.read_bytes()) != seal['prediction_sha256']:
            raise ValueError('Prediction seal mismatch: ' + split)
        ledger = out / f'{split}_COST_LEDGER.jsonl.gz'
        if sha(ledger.read_bytes()) != seal['cost_ledger_sha256']:
            raise ValueError('Cost ledger seal mismatch: ' + split)
        hashes[path.name] = seal['prediction_sha256']
        hashes[ledger.name] = seal['cost_ledger_sha256']
    all_rows, full_rows, input_counts, raw_status_counts = [], [], {}, Counter()
    negative_groups = Counter()
    for split in SPLITS:
        registry_path = out / f'{split}_QUERY_REGISTRY.csv'
        with registry_path.open(encoding='utf-8-sig', newline='') as stream:
            registry = list(csv.DictReader(stream))
        truth_path = out / 'oracle' / f'{split}.json'
        full_path = out / 'evaluation_only' / f'{split}_FULL.json'
        truth, full = read_json(truth_path), read_json(full_path)
        qids = {q['query_id'] for q in registry}
        if not qids <= set(truth) or not qids <= set(full):
            raise ValueError('Oracle or Full missing registered query: ' + split)
        if len(qids) != len(registry):
            raise ValueError('Duplicate registry query ID')
        for path in (registry_path, truth_path, full_path):
            hashes[path.relative_to(out).as_posix()] = sha(path.read_bytes())
        full_rows.extend(_full_summary(registry, truth, full, split))
        count = 0
        with gzip.open(out / f'{split}_PREDICTIONS.jsonl.gz', 'rt', encoding='utf-8') as stream:
            for line in stream:
                pred = json.loads(line)
                if pred['query_id'] not in qids or pred['budget'] not in budgets:
                    raise ValueError('Unregistered replay query or budget')
                row = {key: pred[key] for key in ('split', 'query_id', 'unit', 'family_id', 'metric', 'mechanism', 'condition', 'budget')}
                row.update(policy_family=_policy(pred['policy']))
                row.update(_measure(pred, truth[pred['query_id']], full[pred['query_id']], pred['metric']))
                all_rows.append(row)
                raw_status_counts[(split, pred['policy'], pred['status'])] += 1
                if pred['status'] != 'point':
                    negative_groups[(split, pred['metric'], pred['status'], pred.get('reason') or '(none)')] += 1
                if row['wrong_point']:
                    negative_groups[(split, pred['metric'], 'wrong_point', pred.get('reason') or '(none)')] += 1
                count += 1
        input_counts[split] = {'families': len({q['family_id'] for q in registry}),
                               'logical_units': len({q['unit'] for q in registry}),
                               'queries': len(registry), 'repeated_prediction_rows': count,
                               'point_oracle_queries': sum(truth[q]['status'] == 'point' for q in qids),
                               'unknown_oracle_queries': sum(truth[q]['status'] in ('unknown','bounded','error','analysis_error') for q in qids),
                               'not_applicable_oracle_queries': sum(truth[q]['status'] == 'not_applicable' for q in qids)}
    collapsed = _collapse_repeats(all_rows)
    families = _family_tables(collapsed)
    curves = _aggregate(families)
    write_csv(out / 'FAMILY_METRIC_MECHANISM_BUDGET_POLICY.csv', families)
    write_csv(out / 'AGGREGATE_CURVES.csv', curves)
    write_csv(out / 'FULL_INDEPENDENT_ORACLE.csv', full_rows)
    write_csv(out / 'STATUS_AND_FAILURE_TYPES.csv',
              [dict(zip(('split','metric','status','reason'), key), repeated_rows=count)
               for key, count in sorted(negative_groups.items())])
    static = _compare(curves, families, budgets, 'metric_static', 'global_fixed')
    dynamic = _compare(curves, families, budgets, 'dependency_guided', 'metric_static')
    comparisons = [static, dynamic]
    pair_rows = [dict(comparison=comparison['treatment'] + '_minus_' + comparison['baseline'], **row)
                 for comparison in comparisons for row in comparison.get('paired_families', [])]
    write_csv(out / 'PAIRED_FAMILY_AUC.csv', pair_rows)
    heldout_core = [r for r in full_rows if r['split'] == 'heldout' and r['metric'] in ('UEA','TaskSuccess')]
    heldout_predictions = [r for r in all_rows if r['split'] == 'heldout']
    wrong = sum(r['wrong_point'] for r in heldout_predictions)
    complete_core = all(r['oracle_point'] == r['queries'] and r['correct_point'] == r['queries'] for r in heldout_core) and len(heldout_core) == 2
    c1 = 'SUPPORTED_IN_SCOPE' if complete_core and wrong == 0 else 'PARTIAL'
    cases, case_types = _cases(out)
    write_json(out / 'REPRESENTATIVE_EXECUTION_CASES.json', {'all_observed_cases': cases, 'case_type_counts': case_types})
    attempts, failures = read_rows(out / 'ATTEMPTS.jsonl'), read_rows(out / 'FAILURES.jsonl')
    if len(attempts) > 192:
        raise ValueError('Actual sandbox attempt count exceeds user budget')
    summary = {
        'status': 'COMPLETED_WITH_DECLARED_LIMITS', 'reported_at': now(),
        'input_counts': input_counts, 'sandbox_executions': len(attempts),
        'sandbox_execution_limit': 192, 'sandbox_remaining': 192-len(attempts),
        'logical_units': sum(v['logical_units'] for v in input_counts.values()),
        'families': sum(v['families'] for v in input_counts.values()),
        'new_model_calls': 0, 'new_judge_calls': 0, 'paid_api_calls': 0,
        'failure_log_entries': len(failures), 'expected_execution_case_types': case_types,
        'source_id': 'stdlib-supervised-local-sandbox-v1', 'external_source': 'NOT_AVAILABLE',
        'source_qualification': 'Independent contract oracle unavailable for historical external records; local artifacts do exist.',
        'isolation': 'cooperative licensed-input subprocess isolation; no OS ACL boundary',
        'claims': {'C1': c1, 'C2': static['status'], 'dynamic': dynamic['status']},
        'static_vs_global': static, 'dynamic_vs_static': dynamic,
        'heldout_wrong_point_repeated_rows': int(wrong),
        'heldout_wrong_safe_repeated_rows': int(sum(r['wrong_safe'] for r in heldout_predictions)),
        'full_independent_oracle': full_rows,
        'budgets': budgets, 'auc_interval': [budgets[0], budgets[-1]],
        'auc_definition': 'trapezoidal coverage integrated over common frozen absolute-byte interval and divided by interval width',
        'aggregation': 'Average random order and missing-mask seeds within query/condition first; aggregate within family; equal mean across families with point-reference denominator. All infeasible queries remain in common oracle denominators.',
        'independence_warning': '48 logical units share 12 families; query/mask/budget/policy rows are repeated measurements, not independent samples.',
        'unsupported_metrics': {'ALR': 'unknown; no actual agent reason/identity-neutral contrast',
                                'RIR': 'unknown; no established contaminated-prefix influence/causal contrast',
                                'CI': 'not evaluated as new causal truth'},
        'input_sha256': hashes,
    }
    summary['plot'] = _figure(out / 'BUDGET_COVERAGE.svg', curves, budgets)
    _write_narrative(out, summary, curves, full_rows, cases)
    write_json(out / 'SUMMARY.json', summary)
    return summary


def _write_narrative(out, summary, curves, full_rows, cases):
    c1, static, dynamic = summary['claims']['C1'], summary['static_vs_global'], summary['dynamic_vs_static']
    claim_text = f'''# 主张—证据矩阵

| 主张 | 状态 | 当前证据与限制 |
|---|---|---|
| C1：有限合同下独立受控执行记录的可靠判断 | {c1} | 两个可独立参照的合同是 UEA 与 TaskSuccess；所有缺证/不可行分母保留。只适用于具名家族和许可接口，不是一般 soundness。 |
| C2：指标静态在同总字节预算下优于全局固定顺序 | {static['status']} | 留出正确覆盖 AUC 差 {_number(static.get('auc_difference'))}；完整逐族差异在 PAIRED_FAMILY_AUC.csv。不能外推在线时延或经济节省。 |
| 动态策略优于强指标静态 | {dynamic['status']} | 留出 AUC 差 {_number(dynamic.get('auc_difference'))}。不支持时删除动态算法优势，保留负结果。 |
| 跨真实 agent / 外部 harness 泛化 | UNSUPPORTED | 本轮 source 为标准库受控程序；历史 ClawTrojan/OpenClaw 记录不满足本轮独立合同参照要求。 |
| ALR/RIR/CI 新机制真值或因果主张 | UNSUPPORTED | ALR/RIR 独立 reason/prefix/intervention 条件缺失；CI 仅保留历史依赖回归，没有新语义中和真值。 |

Full 只作为完整观察比较器，单列 [FULL_INDEPENDENT_ORACLE.csv](FULL_INDEPENDENT_ORACLE.csv)，不作为免费补证策略或真值。unknown、bounded、N/A、error 和未知参照均未计入正确回答。

统计单位为 12 个家族、48 个独立初始化的逻辑单元；只有 6 个留出家族，不给 query 独立 Bernoulli 区间、不报显著性。随机 seed、budget、mask、policy 是重复测量。成本仅为包含初始头部、许可初始包、补证包及 padding 的规范化序列化负载代理。

## 可直接使用的保守措辞

- 若 C1 在本轮范围内成立：“在六个留出任务家族和声明的受控持久效果合同中，我们同时报告正确确定判断覆盖与错误确定判断率；结论限于这些程序、记录器和许可观察接口，不表示真实 agent 平台的普适正确性。”
- 阴性结果：“在预先冻结的共同字节阈值及相同初始证据下，动态策略未获支持的优势不作为贡献；强静态方案与全部失败、未知及不可行行一并保留。”
- 来源不足：“本地存在外部 harness 历史轨迹，但它们缺乏本轮所需的独立结构化授权或任务参照。新增验证因此定位为受控程序执行与独立代码路径验证。”
'''
    (out / 'CLAIM_EVIDENCE_MATRIX.md').write_text(claim_text, encoding='utf-8')
    text = ['# 本轮实际结果与论文边界', '',
            f"状态：`{summary['status']}`。实际执行 {summary['sandbox_executions']} 次 / 上限 192 次，逻辑单元 {summary['logical_units']}、家族 {summary['families']}；新增模型、Judge、付费 API 调用均为 0。",
            '', '## 主表 1：完整观察与独立参照', '',
            '| 划分 | 指标 | query | 点参照 | 正确点判断 | 错误点判断 | 未知参照 |',
            '|---|---|---:|---:|---:|---:|---:|']
    for row in full_rows:
        if row['metric'] == 'ALL':
            continue
        text.append(f"| {row['split']} | {row['metric']} | {row['queries']} | {row['oracle_point']:.0f} | {row['correct_point']:.0f} | {row['wrong_point']:.0f} | {row['oracle_unknown']:.0f} |")
    text.extend(['', 'Full 为同一 predictor 的完整观察输出；这里用独立实际状态与权限/任务参照核对，不将 Full 本身视为真值。', '',
                 '## 主表 2：留出共同预算结果', '',
                 '| 策略 | 归一化正确覆盖 AUC | 最大预算正确覆盖 | 最大预算错误确定率 | 最大预算选择性错误率 |',
                 '|---|---:|---:|---:|---:|'])
    main = [r for r in curves if r['split']=='heldout' and r['metric']=='ALL' and r['mechanism']=='ALL']
    for policy in sorted({r['policy'] for r in main}):
        rr = [r for r in main if r['policy']==policy]
        last = max(rr, key=lambda r:r['budget'])
        area = _auc(rr, 'budget', 'family_equal_correct_point_coverage', summary['budgets'])
        text.append(f"| {policy} | {_number(area)} | {_percentage(last['family_equal_correct_point_coverage'])} | {_percentage(last['family_equal_wrong_point_rate'])} | {_percentage(last['family_equal_selective_error_rate'])} |")
    text.extend(['', '![留出预算曲线](BUDGET_COVERAGE.svg)', '',
                 f"静态对全局固定：`{static['status']}`，正确覆盖 AUC 差 {_number(static.get('auc_difference'))}；动态对静态：`{dynamic['status']}`，AUC 差 {_number(dynamic.get('auc_difference'))}。",
                 '', '主表先在同 query/condition 内平均随机顺序与缺失 seeds，再在族内聚合、族间等权。0 预算和其它不足初始负载的行均保留为 infeasible；不会从正确率共同分母中删除。完整条件/指标/族曲线见 CSV。', '',
                 '## 实际执行与采集案例', ''])
    chosen = []
    for kind in ('actual_persistent_effect_without_collector_ack','actual_artifact_with_wrong_task_binding','attempt_without_persistent_effect'):
        matches = [c for c in cases if c['case_type']==kind]
        if matches:
            chosen.append(matches[0])
    if chosen:
        for c in chosen:
            text.append(f"- `{c['execution_unit_id']}`：`{c['case_type']}`；实际持久变化 {c['persistent_change_count']} 个、collector ACK={c['collector_ack_present']}、进程退出码={c['process_returncode']}。原始证据：[{c['record_path']}]({c['record_path']})。")
        text.extend(['', '这些是预设干预下真实本地状态与采集过程的观察：动作尝试、实际落地、ACK 和任务绑定是不同证据。它们不提供自然故障发生率，不证明外部模型攻击。'])
    else:
        text.append('未找到满足条件的原始执行案例，不能从字段设计单独声称出现非平凡执行现象。')
    text.extend(['', '## 失败、未知和来源不足', '',
                 f"失败日志条目 {summary['failure_log_entries']}；预设执行负例类别：`{json.dumps(summary['expected_execution_case_types'], ensure_ascii=False)}`。所有判断原因类型见 STATUS_AND_FAILURE_TYPES.csv，逐实例预测仍保留在原始压缩 JSONL。",
                 '', 'ALR/RIR 参照保持 unknown；CI 没有新增语义真值。外部来源缺乏本轮独立合同参照，新增执行仅来自受控本地程序。无一般三值逻辑创新、全局最小证据或顶会算法有效性结论。', '',
                 '隔离是合作式 stdin 输入边界，同一 OS 身份仍可能读取文件，不宣称抵御恶意策略进程。原始字节与 oracle 独立文件隔离仅服务本轮诚信实现验证。', '',
                 f"图为独立制品；绘图后端为 `{summary['plot']['backend']}`，版本和依赖安装命令见 PLOT_ENVIRONMENT.json。它没有置信区间，也不把重复 query 行当作独立样本。", '',
                 '## 文件', '',
                 '- `SUMMARY.json`：实际数量、支持状态、AUC、输入哈希。',
                 '- `FAMILY_METRIC_MECHANISM_BUDGET_POLICY.csv`：逐族、指标、缺证机制、预算与策略。',
                 '- `AGGREGATE_CURVES.csv`：族等权及 pooled 分母并列。',
                 '- `PAIRED_FAMILY_AUC.csv`：留出逐族配对差异，无不当显著性。',
                 '- `FULL_INDEPENDENT_ORACLE.csv`：完整观察比较器与独立参照分开核对。',
                 '- `STATUS_AND_FAILURE_TYPES.csv`：所有非点状态与错误原因计数。',
                 '- `REPRESENTATIVE_EXECUTION_CASES.json`：实际原始落地/绑定/采集案例。'])
    (out / 'RESULTS_CN.md').write_text('\n'.join(text)+'\n', encoding='utf-8')
    reproduce = '''# 复现边界与环境

本目录包含冻结 PLAN、预测封存、独立 oracle、原始执行和计费账本。应先核对 SUMMARY.json 的 input_sha256，再复算统计；不得为复算图表重新执行业务沙箱或调用模型。

已有环境：PowerShell 7，Python 3.12.14；代码以标准库运行，使用工作区 E 盘的临时目录和 PYTHONDONTWRITEBYTECODE=1。报告入口为 `experiments.evidence_contract_validation.reporting.report(output_directory)`。

报告拒绝覆盖已经存在的 SUMMARY.json。若要独立复算，请把已封存输入复制到一个新的 E 盘输出目录，然后运行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
& 'E:\\Skill ＆ Harness\\Agent\\.venv-skillflow\\Scripts\\python.exe' -B -c "from experiments.evidence_contract_validation.reporting import report; report(r'E:\\已复制的本轮封存输入目录')"
```

需复制的输入：PLAN.json、ATTEMPTS.jsonl、FAILURES.jsonl（存在时）、两划分 QUERY_REGISTRY.csv、PREDICTIONS.jsonl.gz、COST_LEDGER.jsonl.gz、TRAJECTORY_SEAL.json，以及 oracle/、evaluation_only/ 和本轮原始 raw 记录目录。保留目录相对结构。不要复制 SUMMARY.json 或其它生成报告以免混淆。

模型调用始终为 0。完整实验从开发冻结到留出的实际命令和偏差以同目录阶段日志及根 README 为准；报告程序不承担新增实验调度。
'''
    (out / 'REPRODUCE.md').write_text(reproduce, encoding='utf-8')
