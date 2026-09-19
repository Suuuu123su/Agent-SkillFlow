#!/usr/bin/env python3
"""Post-pilot finite-reference check; policies and v1 code stay unchanged."""
import argparse
import json
import time
from pathlib import Path
import run as pilot

DEFAULT_OUT = pilot.ROOT / '论文材料/修复与补强_20260919/evidence_pilot_reference'


def prepare(out):
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'PLAN.json').exists():
        raise SystemExit('Existing plan: use run or a new --out path.')
    template_path = pilot.DEFAULT_OUT / 'PLAN.json'
    plan = json.loads(template_path.read_text(encoding='utf-8'))
    data = pilot.archive_data()
    registry = {r['query_id']: r for r in pilot.json_rows(data['QUERY_REGISTRY.jsonl'])}
    selected = [q for q in pilot.json_rows(data['minimal_data/PREDICTOR_QUERIES.jsonl'])
                if q['metric'] in pilot.METRICS and registry[q['query_id']]['domain'] == 'CONTROLLED_CONSTRUCT']
    selected.sort(key=lambda q: q['query_id'])
    assert len(selected) <= 240  # preserves v1 runner's original bound
    plan.update({
        'version': 'evidence-recovery-finite-reference-extension-v1',
        'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'selection_rule': 'all CONTROLLED_CONSTRUCT queries in frozen v1 metrics; sorted query_id; includes all unknown/ineligible cases; no predictor/gold filtering',
        'selected_query_ids': [q['query_id'] for q in selected],
        'query_count': len(selected),
        'runner_sha256': pilot.digest(Path(pilot.__file__).read_bytes()),
        'reference_wrapper_sha256': pilot.digest(Path(__file__).read_bytes()),
        'parent_plan_sha256': pilot.digest(template_path.read_bytes()),
        'archive_sha256': pilot.digest(pilot.ARCHIVE.read_bytes()),
        'member_sha256': {k: pilot.digest(v) for k, v in data.items()},
        'statistical_unit': 'finite-construct checks: 235 queries over 36 branch units in nine named construct families; same-family, per-request, protocol and horizon dependence; overlapping v1 queries; not 235 independent tasks',
        'extension_disclosure': 'Planned after seeing v1 pilot outcomes because v1 retained only five point-reference labels; this is an expanded finite-reference check, not an untouched validation set. No priority, policy, seed, budget or metric changed.',
        'scope_limits': plan['scope_limits'] + ['no held-out natural-task validation claim', 'no additional independent-data claim'],
    })
    pilot.save_json(out / 'PLAN.json', plan)
    (out / 'PLAN.sha256').write_text(pilot.digest((out / 'PLAN.json').read_bytes()) + '\n', encoding='ascii')
    print(json.dumps({'queries': len(selected), 'plan': str(out / 'PLAN.json')}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.out.resolve()
    if args.action == 'prepare':
        prepare(out)
    else:
        plan = json.loads((out / 'PLAN.json').read_text(encoding='utf-8'))
        assert plan['reference_wrapper_sha256'] == pilot.digest(Path(__file__).read_bytes())
        pilot.run(out)


if __name__ == '__main__':
    main()
