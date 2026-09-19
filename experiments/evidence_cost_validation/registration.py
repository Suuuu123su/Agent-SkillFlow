"""Freeze diagnostic costs and gates before inspecting their outcome comparisons."""
import argparse
from collections import Counter
from pathlib import Path

from experiments.evidence_contract_validation.common import (
    ROOT, CHANNELS, SEEDS, canonical, frozen_json, load_frozen, now, read_json, sha)
from experiments.evidence_contract_validation.dependencies import project
from experiments.evidence_contract_validation.masks import conditions
from experiments.closeout_pilot.reanalysis import check_map, file_map


OLD = '论文材料/证据合同补强_20260919/strengthening-20260919-085337'
CLOSEOUT = '论文材料/补证收口与能力先导_20260919/closeout-pilot-20260919-1100/closeout'


def register(out):
    old, corrected = ROOT/OLD, ROOT/CLOSEOUT
    parent, prior = load_frozen(old/'FINAL_PLAN.json'), load_frozen(corrected/'CLOSEOUT_PLAN.json')
    check_map(old, prior['original_inputs'])
    check_map(ROOT, prior['source_hashes'])
    assert read_json(out/'PARENT_READ_ONLY_VERIFICATION.json')['status'] == 'PASSED'
    quotes = parent['quotes']; assert set(quotes) == set(CHANNELS)
    documents = read_json(old/'licensed_source/development.json')
    headers = {unit:len(canonical(dict(document=project(doc, set()), quotes=quotes,
                                    transport='padded-canonical-v1'))) for unit, doc in documents.items()}
    H = max(headers.values()) + 1024
    S1, S2 = H + sum(quotes.values()), 1 + len(CHANNELS)
    candidates = read_json(old/'STATIC_CANDIDATES_REVISION1.json')
    assert max(Counter(r['metric'] for r in candidates).values()) <= 24
    costs = {
        'C0':dict(unit='historical padded wire bytes', public='actual historical header', quotes=quotes,
                  budgets=parent['budgets'], rho=[b/parent['budgets'][-1] for b in parent['budgets']]),
        'C1':dict(unit='fixed-overhead weighted proxy units', public=H, quotes=quotes, scale=S1,
                  budgets=[i*S1//20 for i in range(21)], rho=[i/20 for i in range(21)]),
        'C2':dict(unit='channel proxy units', public=1, quotes={c:1 for c in CHANNELS}, scale=S2,
                  budgets=list(range(S2+1)), rho=[i/S2 for i in range(S2+1)])}
    masks = {split:{q['query_id']:conditions(q['unit'],q['fault_event'])
                   for q in read_json(old/f'{split}_QUERIES.json')} for split in ('development','heldout')}
    frozen_json(out/'MASK_MANIFEST.json', masks)
    frozen_json(out/'COST_CONTRACTS.json', dict(costs=costs,development_header_bytes=headers,
        H_rule='max old development historical public header byte length + 1024',
        wire_quotes=quotes,wire_protocol='unchanged padded-canonical-v1',
        initial='public + all initially visible channels charged; infeasible receives no observation',
        wire='exact original header and padded bundles in separate ledger; proxy is not online cost',
        overflow='stop INVALID/unsupported frozen wire contract; never increase quotes from hidden payloads'))
    fresh_seeds=[2026091901,2026091902,2026091903]; assert not set(fresh_seeds)&set(SEEDS)
    sources=dict(prior['source_hashes'])
    sources.update({p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in Path(__file__).parent.glob('*.py')})
    plan=dict(version='a-cost-diagnostic-v1',frozen_at=now(),base_commit='be2bc1f705687062421ea06b762dc8a649179c97',
        old_run=OLD,corrected_run=CLOSEOUT,original_inputs=prior['original_inputs'],
        corrected_inputs=file_map(corrected),source_hashes=sources,
        cost_contract_sha256=sha((out/'COST_CONTRACTS.json').read_bytes()),
        mask_manifest_sha256=sha((out/'MASK_MANIFEST.json').read_bytes()),
        candidate_sha256=sha((old/'STATIC_CANDIDATES_REVISION1.json').read_bytes()),
        candidates=[{k:r[k] for k in ('metric','candidate_index','order')} for r in candidates],
        costs=costs,missing_seeds=list(SEEDS),fresh_missing_seeds=fresh_seeds,
        policies=['global_fixed','metric_static','dependency_guided'],
        static_selection='old development only: -raw wrong, family equal seed averaged normalized rho trapezoid AUC, -seed weighted decision cost, -original candidate index',
        no_point_truth_fallback='AUC remains null; rank as zero solely for unchanged deterministic cost/index fallback, not a claimed score',
        dynamic='unaltered PR2 predictor + original choose, same base order as selected static for this cost',
        aggregation='seed mean within query/condition then family rates then family equal; common point-truth denominator retains infeasible, unknown truth separate',
        attribution=dict(tolerance=1e-10,classes=['benefit','harm','same'],
            exclusive_dependency_group='first divergent dynamic channel (or no_divergence); cross-tab with metric/condition; no repeated-area counting',
            area='paired correct indicator times seed weight divided by point query-condition count in family and family count, trapezoid on common grid',
            representatives='up to four deterministic cases: greatest positive area; greatest negative area if exists; lexicographic same; known H01 lifecycle case',
            necessity='delete acquired prerequisite via frozen project and re-predict; oracle unchanged, offline only'),
        gate_A=dict(tolerance=1e-12,both_costs_required=True,auc_difference_min_exclusive=1e-12,
            positive_families_min=5,families=6,each_leave_one_out_positive=True,C1_positive_interior_points_min=2,
            C2_positive_interior_points_min=1,dependency_recovery_witness_required=True,
            errors='no additional wrong point or wrong safe; all new replay errors must be zero',
            integrity_required=True,failure='C1 pass C2 fail COST_SENSITIVE; both nonpositive NO_GAIN; otherwise SMALL_OR_UNSTABLE; unsupported truth INCONCLUSIVE; audit fail INVALID'),
        gate_B=dict(replicated='both positive; >=5/6 positive each; all leave-one-out positive; zero extra wrong/safe; >=2 families have static unknown/dynamic correct at interior budgets',
            promising_C1_auc_min=0.001,promising_C1_coverage_min=0.005,promising_interior_points_min=2,
            incomplete='INCONCLUSIVE',post_outcome_semantic_bug='INVALID; retain batch; no confirmatory reuse'),
        fresh_selection=dict(rule='fixed six different operation/checker semantics chosen for file/log/directory/package/inventory/SQL coverage, not ranked by E1/E2 gain',
            families=['D01_append_journal','D03_render_report','H01_publish_directory','H02_inventory_reservation','H03_manifest_package','H04_sql_join_export'],
            interpretation='new instances in old families, not unseen mechanisms',
            cells=['valid_commit','valid_no_commit','invalid_commit','invalid_no_commit'],
            invalid_grant='exact resource mismatch for all families, fixed before outcomes',
            execution='orthogonal pre-commit stop versus actual commit; unchanged predictor/contract/oracle',
            input_seed=2026091904,neutral_unit_ids='N00001..N00024',primary_metrics=['UEA','TaskSuccess'],
            new_input_path_session=True,same_author_bias=True,mask_mechanisms='unchanged 10 whole-channel + 3 random counts averaged over 3 seeds + 1 failure-correlated condition'),
        resources=dict(new_business_cap=48,formal_units=24,sanity_cap=4,infrastructure_retry_reserve=20,
            retry_per_unit=1,actions_per_attempt_cap=16,model_calls=0,judge_calls=0,paid_api_calls=0,GPU=0),
        scope='E1/E2 already disclosed exploratory data; no B; no third cost; no dynamic tuning; no automatic expansion',
        implementation_binding='additional implementation modules sealed before any comparison in IMPLEMENTATION_SEAL.json; these registered definitions never change')
    frozen_json(out/'DIAGNOSTIC_PLAN.json',plan)
    print({'H':H,'S1':S1,'S2':S2,'status':'FROZEN','new_executions':0})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();register(a.out.resolve())
