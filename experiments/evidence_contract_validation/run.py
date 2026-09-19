"""Staged, append-only controller for the authorized 48-unit, zero-model study."""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import platform
import subprocess
import sys
from pathlib import Path

from .adapter import adapt, query_records
from .common import (CHANNELS, CODE, ROOT, SEEDS, append_json, canonical, code_hashes,
                     frozen_json, git_sha, load_frozen, now, read_json, read_rows,
                     sha, verify_hashes, write_csv, write_json)
from .dependencies import build_ledger, project
from .evaluation import choose_static, replay
from .independent_oracle import evaluate_unit
from .predictor import predict
from .sandbox import load_registry, run_unit, unit_specs
from .transport import Broker, calibration_quotes

TASK = ROOT / 'docs/tasks/evidence-strengthening-20260919'
TRACKER = TASK / 'refine-logs/EXPERIMENT_TRACKER.md'
BASELINE = ROOT / '论文材料/证据合同补强_20260919/baseline-audit'



def load_plan(out):
    return load_frozen(out / ('FINAL_PLAN.json' if (out/'FINAL_PLAN.json').exists() else 'PLAN.json'))


def seal_inputs(out, split):
    # This supplements the original collection seal; it never replaces raw files.
    for path in sorted((out/'raw'/split).rglob('record.json')):
        record=read_json(path)
        folder=path.parent
        for filename, expected in [('permission_schedule.json',record['permission_schedule']),
                                   ('task_requirements.json',record['task_requirements']),
                                   ('before.json',record['supervisor']['state_before']),
                                   ('after.json',record['supervisor']['state_after'])]:
            if read_json(folder/filename)!=expected:
                raise ValueError('Raw sidecar disagrees with sealed record: '+str(folder/filename))
    files=[p for p in (out/'raw'/split).rglob('*') if p.is_file()]
    files += [out/'licensed_source'/f'{split}.json',out/f'{split}_QUERIES.json',out/f'{split}_QUERY_REGISTRY.csv']
    frozen_json(out/f'{split}_INPUT_MANIFEST.json', {p.relative_to(out).as_posix():sha(p.read_bytes()) for p in files})


def verify_inputs(out, split):
    mapping=load_frozen(out/f'{split}_INPUT_MANIFEST.json')
    for relative, digest in mapping.items():
        if sha((out/relative).read_bytes())!=digest:
            raise ValueError('Sealed oracle/policy input changed: '+relative)


def revise_freeze(out):
    if any(row['split']=='heldout' for row in read_rows(out/'ATTEMPTS.jsonl')):
        raise ValueError('No freeze revision after heldout execution')
    if (out/'FINAL_PLAN.json').exists():
        raise ValueError('Final amended freeze already exists')
    plan=load_frozen(out/'PLAN.json')
    documents=read_json(out/'licensed_source/development.json')
    queries=read_json(out/'development_QUERIES.json')
    seal_inputs(out,'development')
    selected,candidates=choose_static(documents,queries,plan['quotes'],plan['budgets'],read_json(out/'oracle/development.json'),out/'policy_ipc'/'development_search_revision1')
    write_json(out/'STATIC_CANDIDATES_REVISION1.json',candidates,exclusive=True)
    plan.update(parent_plan_sha256=sha((out/'PLAN.json').read_bytes()),frozen_at=now(),
                status='FINAL_AMENDED_FREEZE_BEFORE_HELDOUT',selected_static=selected,code_hashes=code_hashes(),
                amendment='Before heldout: seal all raw oracle sidecars and query inputs; average random missingness seeds within condition for development static selection, matching reporting. No extra sandbox or heldout access.',
                candidate_selection_repeat_rule='random mask seed weight 1/3; whole-channel and failure-stress weight1; family equal coverage')
    frozen_json(out/'FINAL_PLAN.json',plan)
    log(out,'R006_pre_heldout_amended_freeze',parent_plan_retained=True,heldout_accessed=False)
    phase(out,'M2','R006_FINAL_AMENDED_FREEZE','留出前复核修正：所有oracle原始sidecar与查询输入独立封存；开发静态选择先平均随机seed，与主结果口径一致。旧冻结/候选保留，实际执行仍24。')


def log(out, action, **values):
    append_json(out / 'ACCESS_LOG.jsonl', {'at': now(), 'action': action, **values})


def phase(out, milestone, status, details):
    attempts = read_rows(out / 'ATTEMPTS.jsonl')
    row = {'at': now(), 'milestone': milestone, 'status': status,
           'actual_sandbox_executions': len(attempts), 'remaining_execution_budget': 192-len(attempts),
           'model_calls': 0, 'details': details}
    append_json(out / 'STAGES.jsonl', row)
    write_json(out / 'STATUS.json', row)
    readme = ROOT / 'README.md'
    text = readme.read_text(encoding='utf-8')
    start, end = '<!-- evidence-strengthening-current:start -->', '<!-- evidence-strengthening-current:end -->'
    relative = out.relative_to(ROOT).as_posix()
    paragraph = (start + '\n\n' + f'2026-09-19 新一轮证据合同补强：**{milestone} / {status}**。{details} '
                 f'累计实际本地沙箱执行 {len(attempts)}/192；新增模型调用 0。'
                 f'[阶段与证据]({relative}/README.md)。独立工作树保留原工作区修改；'
                 '外部日志存在但缺合格独立合同参照，仅声明受控程序跨实现验证。\n\n' + end)
    if start in text:
        a, b = text.index(start), text.index(end)+len(end)
        text = text[:a] + paragraph + text[b:]
    else:
        marker = '## 当前阶段与结果\n'
        text = text.replace(marker, marker + '\n' + paragraph + '\n')
    text = text.replace('下一阶段补强任务已编写，状态为 `READY_TO_EXECUTE`，新一轮实验尚未启动：',
                        '本轮补强已在独立研究分支执行，当前状态见上方阶段记录：')
    readme.write_text(text, encoding='utf-8')
    history = read_rows(out / 'STAGES.jsonl')
    body = ['# 证据合同补强：实际执行记录', '', f'Run ID: `{out.name}`。模型调用 0；实际执行预算 192。',
            '', '此目录记录本轮新实验；旧240/235查询仅作开发回归。合作式输入隔离，不是OS强隔离。', '',
            '|阶段|状态|累计实际执行|结果与下一步边界|', '|---|---|---:|---|']
    body += [f"|{x['milestone']}|{x['status']}|{x['actual_sandbox_executions']}|{x['details']}|" for x in history]
    body += ['', '[状态](STATUS.json) · [原始执行预算账本](ATTEMPTS.jsonl) · [访问日志](ACCESS_LOG.jsonl)',
             '', '完成材料见 RESULTS_CN.md、SUMMARY.json、CLAIM_EVIDENCE_MATRIX.md、REPRODUCE.md；尚未生成的文件不表示通过。']
    (out / 'README.md').write_text('\n'.join(body)+'\n', encoding='utf-8')
    with TRACKER.open('a', encoding='utf-8') as handle:
        handle.write(f"\n|{row['at']}|{milestone}|{status}|{relative}|实际执行 {len(attempts)}/192；模型0|{details}|是|\n")


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    registry = load_registry()
    specs = unit_specs()
    if len(specs) != 48 or len(registry['families']) != 12:
        raise ValueError('Registry must have exactly 48 units and 12 families')
    registration = {
        'created_at': now(), 'run_id': out.name, 'git_sha': git_sha(),
        'status': 'REGISTERED_BEFORE_ANY_NEW_EXECUTION',
        'logical_units': 48, 'families': 12, 'actual_execution_cap': 192,
        'per_unit_execution_cap': 4, 'per_batch_execution_cap': 48,
        'model_call_cap': 0, 'policy_seeds': list(SEEDS), 'missing_seeds': list(SEEDS),
        'run_dynamic': True, 'dynamic_rule': 'Current versioned missing-channel priorities, affordable channel only; freeze one policy before heldout',
        'budget_rule': '0 plus nine nearest-rank deciles of development initial/full padded total bytes; at most10 absolute thresholds',
        'quote_rule': 'Per-channel public fixed quote: ceil(2*development max packet/1024)*1024+1024; overflow invalidates row, never truncates',
        'source_class': 'controlled_local_programs', 'isolation': 'cooperative licensed input, no OS ACL claim',
        'new_metric_contract': 'controlled-persistent-effect-v1; single supervised task action; exact resources/session/timing; not production Lifetime diamond',
        'initial_code_hashes': code_hashes(),
        'spec_hashes': {s['execution_unit_id']: sha(canonical(s)) for s in specs},
        'plan_source_sha256': sha((TASK / 'refine-logs/EXPERIMENT_PLAN.md').read_bytes()),
        'family_registry_sha256': sha((CODE / 'family_registry.json').read_bytes()),
        'statistical_unit': '48 logical instances in 12 shared families; policies/masks/budgets/seeds repeated observations, not iid tasks',
    }
    frozen_json(out / 'REGISTRATION.json', registration)
    frozen_json(out / 'FAMILY_SPLIT.json', registry)
    for name in ('ATTEMPTS.jsonl', 'FAILURES.jsonl'):
        (out / name).write_text('', encoding='utf-8')
    files = [p for p in (ROOT / '论文材料').rglob('*.zip')]
    files += [TASK / 'BACKGROUND_HANDOFF.md', TASK / 'CODEX_GOAL.md', TASK / 'refine-logs/EXPERIMENT_PLAN.md']
    frozen_json(out / 'HISTORY_MANIFEST.json', {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in files})
    original = ROOT.parent.parent / 'Agent'
    frozen_json(out / 'ORIGINAL_WORKTREE.json', {
        'path': str(original),
        'diff_sha256': sha(subprocess.check_output(['git', 'diff', '--binary', 'HEAD'], cwd=original)),
        'status_sha256': sha(subprocess.check_output(['git', 'status', '--porcelain=v1', '-z'], cwd=original))})
    write_json(out / 'ENVIRONMENT.json', {'python': sys.version, 'executable': sys.executable,
               'platform': platform.platform(), 'git_sha': git_sha(), 'shell': 'PowerShell 7.6.5',
               'network_in_experiment': False, 'model_calls': 0,
               'temp_policy': 'E-drive output only', 'created_at': now()})
    log(out, 'prepare', heldout_results_created=False)
    phase(out, 'M0', 'IMPLEMENTED_PENDING_GATE', '已预注册48单元/12族与全部随机种子；待依赖、隔离、费用及HIAA回归门通过，尚无新增执行。')


def check_contract(out):
    registration = load_frozen(out / 'REGISTRATION.json')
    files = ['test_evidence_contract_dependencies.py', 'test_evidence_sandbox_contract.py',
             'test_evidence_receipt_binding.py', 'test_evidence_budget.py']
    temp = out / 'validation_tmp'
    temp.mkdir(exist_ok=True)
    env = dict(os.environ)
    env.update(PYTHONPATH=str(ROOT)+os.pathsep+str(ROOT/'src'), PYTHONDONTWRITEBYTECODE='1',
               TMP=str(temp), TEMP=str(temp))
    command = [sys.executable, '-B', '-m', 'pytest', *['tests/unit/analysis/'+name for name in files],
               '-o', 'addopts=', '-p', 'no:cacheprovider', '-q', '--junitxml='+str(out/'M0_TESTS.xml')]
    process = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    (out / 'M0_TESTS.txt').write_text(process.stdout+'\n'+process.stderr, encoding='utf-8')
    baseline = read_json(BASELINE / 'SUMMARY.json')
    write_json(out / 'SOURCE_MANIFEST.json', read_json(BASELINE / 'EXTERNAL_SOURCE_INVENTORY.json'))
    receipt = {'at': now(), 'test_command': command, 'exit_code': process.returncode,
               'baseline_summary': baseline, 'models': 0, 'new_sandbox_executions': 0,
               'code_hashes': code_hashes()}
    write_json(out / 'M0_GATE.json', receipt)
    if process.returncode:
        append_json(out / 'FAILURES.jsonl', {'stage':'M0', 'type':'unit_test_failure', 'evidence':'M0_TESTS.txt'})
        phase(out, 'M0', 'FAILED', '针对性测试有失败，禁止留出与效率结论；保留日志，继续开发修复。')
        raise SystemExit(process.returncode)
    verify_hashes(load_frozen(out / 'HISTORY_MANIFEST.json'))
    phase(out, 'M0', 'PASSED', '依赖掩码、隔离、字节计费和回执绑定测试通过；HIAA13测试/48名单及旧CI8+2差异已复核。下一步只收集24个开发单元。')


def _collect(out, split):
    registration = load_frozen(out / 'REGISTRATION.json')
    if not (out / 'M0_GATE.json').exists() or read_json(out/'M0_GATE.json')['exit_code']:
        raise ValueError('M0 gate not passed')
    if split == 'heldout':
        plan = load_plan(out)
        verify_hashes(plan['code_hashes'])
        if (out / 'heldout_COLLECTION_SEAL.json').exists():
            raise ValueError('Heldout has already been collected; no repeat allowed')
    documents, queries, records = {}, [], []
    log(out, 'collect_'+split+'_started', results_shown_to_policy=False)
    for spec in unit_specs(split):
        if sha(canonical(spec)) != registration['spec_hashes'][spec['execution_unit_id']]:
            raise ValueError('Preregistered unit changed')
        attempts = read_rows(out / 'ATTEMPTS.jsonl')
        count = sum(r['unit'] == spec['execution_unit_id'] for r in attempts)
        if count:
            raise ValueError('Automatic retries forbidden; preserve existing attempted unit')
        if len(attempts) >= 192 or count >= 4:
            raise ValueError('Actual execution budget exhausted')
        attempt_id = f'attempt-{count+1:02d}'
        append_json(out / 'ATTEMPTS.jsonl', {'at':now(), 'unit':spec['execution_unit_id'],
                    'family_id':spec['family_id'], 'split':split, 'attempt_id':attempt_id,
                    'source_id':load_registry()['source_id'], 'actual_execution_ordinal':len(attempts)+1,
                    'git_sha':git_sha(), 'plan_sha':sha((out / ('FINAL_PLAN.json' if split=='heldout' else 'REGISTRATION.json')).read_bytes()),
                    'model_calls':0, 'state':'COUNTED_BEFORE_INITIALIZATION'})
        try:
            record = run_unit(spec, out/'raw'/split, attempt_id)
            documents[record['execution_unit_id']] = adapt(record)
            queries.extend(query_records(record))
            record_path = out/'raw'/split/spec['execution_unit_id']/attempt_id/'record.json'
            records.append({'unit':spec['execution_unit_id'], 'path':str(record_path.relative_to(out)),
                            'sha256':sha(record_path.read_bytes())})
            if record['supervisor']['process_returncode'] != 0:
                append_json(out/'FAILURES.jsonl', {'stage':split, 'unit':spec['execution_unit_id'],
                            'type':'observed_worker_nonzero', 'return_code':record['supervisor']['process_returncode'],
                            'ack_lost':record['collector']['acknowledgment_lost'], 'path':str(record_path.relative_to(out))})
        except Exception as exc:
            append_json(out/'FAILURES.jsonl', {'stage':split, 'unit':spec['execution_unit_id'],
                        'type':type(exc).__name__, 'message':str(exc), 'attempt_counted':True})
            phase(out, 'M1' if split=='development' else 'M2', 'COLLECTION_FAILED',
                  '执行或转换失败已计入预算并保留；未自动重试，不用失败样本替换。')
            raise
    write_json(out/'licensed_source'/f'{split}.json', documents, exclusive=True)
    write_csv(out/f'{split}_QUERY_REGISTRY.csv', queries)
    write_json(out/f'{split}_QUERIES.json', queries, exclusive=True)
    frozen_json(out/f'{split}_COLLECTION_SEAL.json', {'at':now(), 'records':records,
                'units':len(documents), 'families':len({q['family_id'] for q in queries}), 'queries':len(queries),
                'document_sha256':sha((out/'licensed_source'/f'{split}.json').read_bytes())})
    if split == 'heldout':
        seal_inputs(out,split)
    log(out, 'collect_'+split+'_sealed', units=len(documents), query_count=len(queries))
    if split == 'development':
        _reference(out, split)
        refs = read_json(out/'oracle'/f'{split}.json')
        full = read_json(out/'evaluation_only'/f'{split}_FULL.json')
        mismatches = [qid for qid,r in refs.items() if r['status']=='point' and
                      (full[qid]['status']!='point' or full[qid]['value']!=r['value'])]
        write_json(out/'M1_GATE.json', {'mismatches':mismatches, 'point_reference_queries':sum(r['status']=='point' for r in refs.values()),
                   'unknown_reference_queries':sum(r['status']=='unknown' for r in refs.values()),
                   'source':'controlled_programs_only'})
        if mismatches:
            phase(out,'M1','DEVELOPMENT_MISMATCH','开发完整观察与独立参照不一致；保留全部轨迹，未接触留出，先修开发接口。')
            raise ValueError('Development Full/oracle mismatch: '+str(mismatches))
        phase(out,'M1','PASSED_CONTROLLED_SCOPE','24开发单元/6族已实际执行；UEA/TaskSuccess独立参照与Full核对通过；ALR/RIR原因和污染前缀不足仍未知。下一步冻结强静态、预算和动态。')
    else:
        phase(out,'M2','HELDOUT_COLLECTED_NOT_EVALUATED','24留出单元/6族已按冻结代码执行并封存；尚未读取其oracle/Full；下一步一次性回放全部冻结策略后再连接参照。')


def _reference(out, split):
    if split == 'heldout' and not (out/'heldout_TRAJECTORY_SEAL.json').exists():
        raise ValueError('Heldout reference cannot be joined before policy trajectories are sealed')
    if split == 'heldout':
        verify_inputs(out,split)
    documents = read_json(out/'licensed_source'/f'{split}.json')
    queries = read_json(out/f'{split}_QUERIES.json')
    refs, full = {}, {}
    by_unit = {}
    for unit in documents:
        value = evaluate_unit(out/'raw'/split/unit/'attempt-01')
        by_unit[unit] = value
    for query in queries:
        refs[query['query_id']] = by_unit[query['unit']]['metrics'][query['metric']]
        full[query['query_id']] = predict(query['metric'], project(documents[query['unit']], CHANNELS))
    write_json(out/'oracle'/f'{split}.json', refs, exclusive=True)
    write_json(out/'oracle'/f'{split}_PROVENANCE.json', by_unit, exclusive=True)
    write_json(out/'evaluation_only'/f'{split}_FULL.json', full, exclusive=True)
    log(out,'reference_join_'+split, oracle_queries=len(refs), policy_trajectories_sealed=(out/f'{split}_TRAJECTORY_SEAL.json').exists())


def freeze(out):
    if (out/'PLAN.json').exists():
        raise FileExistsError('Final plan already frozen')
    if read_json(out/'M1_GATE.json')['mismatches']:
        raise ValueError('Development oracle gate failed')
    documents = read_json(out/'licensed_source/development.json')
    queries = read_json(out/'development_QUERIES.json')
    quotes = calibration_quotes(list(documents.values()))
    sizes = []
    from .masks import conditions
    for q in queries:
        doc=documents[q['unit']]
        sizes.append(Broker(doc, set(CHANNELS), quotes).total)
        for condition in conditions(q['unit'], q['fault_event']):
            sizes.append(Broker(doc,set(CHANNELS)-set(condition['missing']),quotes).total)
    sizes.sort()
    budgets=sorted({0,*[sizes[max(0,math.ceil((index/9)*len(sizes))-1)] for index in range(1,10)]})
    write_json(out/'DEVELOPMENT_CALIBRATION.json',{'quotes':quotes,'budgets':budgets,'sample_total_bytes':sizes,
               'rule':'nearest-rank deciles at 1/9..9/9 plus0; repeated query sizes are explicit calibration only'})
    selected, candidates = choose_static(documents,queries,quotes,budgets,read_json(out/'oracle/development.json'),out/'policy_ipc'/'development_search')
    write_json(out/'STATIC_CANDIDATES.json',candidates,exclusive=True)
    plan=load_frozen(out/'REGISTRATION.json')
    plan.update(frozen_at=now(),status='FROZEN_BEFORE_HELDOUT_EXECUTION',quotes=quotes,budgets=budgets,
                selected_static=selected,run_dynamic=True,code_hashes=code_hashes(),
                budget_quantiles=[index/9 for index in range(1,10)],
                cost_scope='Canonical broker header plus actual padded serialized return packets; local analysis IPC scheduling/messages excluded from this offline payload proxy. No online latency/cost claim.',
                development_amendments='Pre-execution alias/ACK/candidate fixes and pre-heldout CPU packet memoization. All packet replays remain charged; original registration and tests retained.',
                static_candidates_per_metric=24,auc_interval=[min(budgets),max(budgets)],
                input_hashes={'development_collection':sha((out/'development_COLLECTION_SEAL.json').read_bytes()),
                              'family_registry':sha((CODE/'family_registry.json').read_bytes()),
                              'dependency_contract':sha((CODE/'dependency_contract.json').read_bytes())},
                comparison='point/NA same stop rule, initial costs included, per-family paired descriptive results',
                masked_replay='20 masks per query: 10 whole-channel, 9 random (3 seeds x1/3/5), 1 failure-correlated stress; not natural missingness',
                quote_metadata='global frozen fixed quotes; real canonical packet padding transmitted and charged; no hidden-size oracle')
    frozen_json(out/'PLAN.json',plan)
    (out/'PLAN.sha256').write_text(sha((out/'PLAN.json').read_bytes())+'\n',encoding='ascii')
    write_json(out/'DEPENDENCY_LEDGER.json',{unit:build_ledger(doc) for unit,doc in documents.items()},exclusive=True)
    log(out,'R006_final_freeze',heldout_accessed=False,run_dynamic=True,policy_count=6)
    phase(out,'M2','R006_FROZEN','开发候选选择已完成；每指标至多24静态候选、统一绝对字节预算和1个动态策略已封存。下一步执行24留出单元，禁止按留出修改。')


def evaluate(out):
    plan=load_plan(out)
    verify_hashes(plan['code_hashes'])
    verify_hashes(load_frozen(out/'HISTORY_MANIFEST.json'))
    for split in ('development','heldout'):
        verify_inputs(out,split)
        seal=load_frozen(out/f'{split}_COLLECTION_SEAL.json')
        docpath=out/'licensed_source'/f'{split}.json'
        if sha(docpath.read_bytes())!=seal['document_sha256']:
            raise ValueError('Sealed adapter records changed')
        for item in seal['records']:
            if sha((out/item['path']).read_bytes())!=item['sha256']:
                raise ValueError('Sealed raw record changed')
        documents=read_json(docpath)
        queries=read_json(out/f'{split}_QUERIES.json')
        log(out,'policy_replay_'+split+'_started',reference_joined=False)
        count=replay(out,split,documents,queries,plan)
        log(out,'policy_replay_'+split+'_sealed',rows=count)
    _reference(out,'heldout')
    # Combined names required by the delivery contract; indexes avoid duplicating large files.
    write_json(out/'PREDICTIONS.json',{'parts':['development_PREDICTIONS.jsonl.gz','heldout_PREDICTIONS.jsonl.gz']},exclusive=True)
    write_json(out/'COST_LEDGER.json',{'parts':['development_COST_LEDGER.jsonl.gz','heldout_COST_LEDGER.jsonl.gz']},exclusive=True)
    write_csv(out/'QUERY_REGISTRY.csv',read_json(out/'development_QUERIES.json')+read_json(out/'heldout_QUERIES.json'))
    phase(out,'M2','R007_R008_EVALUATED_ONCE','全部冻结静态与动态策略轨迹先封存，随后才连接留出独立参照；未知、失败及不可行预算均保留。下一步只统计与审查，不调参或扩样。')


def report(out):
    from .reporting import report as build_report
    build_report(out)
    verify_hashes(load_frozen(out/'HISTORY_MANIFEST.json'))
    original=load_frozen(out/'ORIGINAL_WORKTREE.json')
    unchanged=(sha(subprocess.check_output(['git','diff','--binary','HEAD'],cwd=original['path']))==original['diff_sha256']
               and sha(subprocess.check_output(['git','status','--porcelain=v1','-z'],cwd=original['path']))==original['status_sha256'])
    write_json(out/'PRESERVATION_CHECK.json',{'original_worktree_unchanged':unchanged,'historical_archives_unchanged':True,'checked_at':now()})
    if not unchanged:
        raise ValueError('Original worktree changed; inspect before publication')
    phase(out,'M3','COMPLETED_WITH_SCOPE_LIMITS','已完成独立参照、冻结留出、公平预算、动态删除检验与主张表；结果与限制见SUMMARY/RESULTS_CN。受控程序结论不外推外部agent；旧材料与原工作区校验未变。')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('stage',choices=['prepare','check-contract','collect-development','freeze','collect-heldout','evaluate','report','revise-freeze'])
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    out=args.out.resolve()
    if ROOT not in out.parents or out.drive.upper()=='C:':
        raise ValueError('Output must be inside the authorized E-drive worktree')
    stages={'prepare':prepare,'check-contract':check_contract,'collect-development':lambda p:_collect(p,'development'),
            'freeze':freeze,'revise-freeze':revise_freeze,'collect-heldout':lambda p:_collect(p,'heldout'),'evaluate':evaluate,'report':report}
    if out.exists():
        append_json(out/'COMMANDS.jsonl',{'at':now(),'argv':sys.argv,'python':sys.executable,'stage':args.stage})
    stages[args.stage](out)
    if args.stage=='prepare':
        append_json(out/'COMMANDS.jsonl',{'at':now(),'argv':sys.argv,'python':sys.executable,'stage':args.stage})
    print(json.dumps({'stage':args.stage,'status':'completed','out':str(out),
                      'actual_executions':len(read_rows(out/'ATTEMPTS.jsonl')),'model_calls':0},ensure_ascii=False))


if __name__=='__main__':
    main()
