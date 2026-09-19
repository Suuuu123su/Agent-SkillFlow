#!/usr/bin/env python3
"""Descriptive reporting and outcome integrity checks; never tunes a policy."""
import argparse
import collections
import csv
import gzip
import json
import statistics
from pathlib import Path
import run as pilot


def rows(path):
    if path.exists():
        with path.open(encoding='utf-8', newline='') as f:
            return list(csv.DictReader(f))
    with gzip.open(str(path) + '.gz', 'rt', encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=pilot.DEFAULT_OUT)
    args = parser.parse_args()
    out = args.out.resolve()
    plan = json.loads((out / 'PLAN.json').read_text())
    status = json.loads((out / 'RUN_STATUS.json').read_text())
    summary = rows(out / 'summary.csv')
    detail = rows(out / 'query_results.csv')
    sample = rows(out / 'sample.csv')
    qids = set(plan['selected_query_ids'])
    assert set(r['query_id'] for r in sample) == qids
    assert set(r['query_id'] for r in detail) == qids
    groups = collections.defaultdict(list)
    for r in detail:
        groups[(r['condition'], r['policy'], r['seed'], r['budget'])].append(r)
    assert all(len(rs) == len(qids) and len({r['query_id'] for r in rs}) == len(qids) for rs in groups.values())
    full = {r['query_id']: r for r in detail if r['policy'] == 'Full'}
    max_budget = [r for r in detail if r['budget'] == '9' and r['policy'] != 'Full']
    mismatch_final = sum(any(r[k] != full[r['query_id']][k] for k in ['status', 'eligibility', 'value']) for r in max_budget)
    assert mismatch_final == 0
    base = collections.defaultdict(set)
    for r in detail:
        if r['budget'] == '0':
            base[(r['query_id'], r['condition'])].add((r['status'], r['eligibility'], r['value']))
    assert all(len(v) == 1 for v in base.values())
    ref_error = [r for r in detail if r['reference_point_correct'] == 'False']
    elig_error = [r for r in detail if r['reference_eligibility_correct'] == 'False']
    unsupported = [r for r in detail if r['status'] == 'point' and r['full_point_equal'] != 'True']
    errors = [r for r in detail if r['status'] == 'analysis_error']
    random_summary = []
    for condition in plan['conditions']:
        for budget in plan['budget']:
            subset = [r for r in summary if r['condition'] == condition and r['policy'] == 'random' and int(r['budget']) == budget]
            row = dict(condition=condition, budget=budget, seeds=len(subset))
            for key in ['point_count', 'point_coverage', 'eligibility_coverage',
                        'unknown_rate', 'mean_acquired_families', 'mean_added_json_bytes']:
                vals = [float(r[key]) for r in subset]
                row.update({key + '_mean': statistics.mean(vals), key + '_min': min(vals), key + '_max': max(vals)})
            random_summary.append(row)
    pilot.save_csv(out / 'random_seed_summary.csv', random_summary)
    indexing = {(r['condition'], r['policy'], int(r['budget'])): r for r in summary if r['policy'] != 'random'}
    paired = []
    for condition in plan['conditions']:
        for budget in plan['budget']:
            a = indexing[condition, 'contract_guided', budget]
            b = indexing[condition, 'metric_fixed', budget]
            paired.append({'condition': condition, 'budget': budget,
                           'guided_minus_static_point_count': int(a['point_count']) - int(b['point_count']),
                           'guided_minus_static_eligibility_coverage': float(a['eligibility_coverage']) - float(b['eligibility_coverage']),
                           'guided_minus_static_mean_families': float(a['mean_acquired_families']) - float(b['mean_acquired_families']),
                           'guided_minus_static_mean_json_bytes': float(a['mean_added_json_bytes']) - float(b['mean_added_json_bytes'])})
    pilot.save_csv(out / 'guided_vs_metric_fixed.csv', paired)
    pilot.save_json(out / 'RESULT_AUDIT.json', {
        'status': 'PASS' if not (ref_error or elig_error or unsupported or errors) else 'CHECK_FINDINGS',
        'queries': len(qids), 'registry_groups': len({r['independence_group'] for r in sample}),
        'distinct_source_units': len({r['unit'] for r in sample}),
        'all_trajectory_groups_have_same_queries': True,
        'identical_initial_state_across_policies': True,
        'max_budget_final_state_disagreements_with_full': mismatch_final,
        'reference_point_errors': len(ref_error), 'reference_eligibility_errors': len(elig_error),
        'points_not_supported_by_full': len(unsupported), 'analysis_errors': len(errors),
        'guided_has_any_more_point_answers_than_metric_static': any(x['guided_minus_static_point_count'] > 0 for x in paired),
        'guidance_is_not_an_independent_accuracy_claim': True,
        'reference_scope': 'controlled finite constructs only; no natural-language human labels',
    })
    fs = status['full_summary']
    ref = 'reference_wrapper_sha256' in plan
    title = '有限构念参照扩展检查' if ref else '合同导向补证离线先导'
    text = [f'# {title}', '',
            f"状态：实际完成。{len(qids)} 条查询，{status['unique_registry_units']} 个来源运行单元；0 次网络、模型或业务工具调用，0 个分析异常。", '',
            '**结果支持合同结构可以指导补证顺序；没有发现当前自适应 missing_evidence 规则超过按指标固定顺序的点值覆盖收益。** 不将这一阴性结果包装成新的自适应算法。', '',
            '## 预先冻结与执行范围', '',
            f"PLAN SHA-256：`{status['plan_sha256']}`。输入 ZIP SHA-256：`{status['archive_sha256']}`。", '',
            '准备阶段先写 PLAN.json 和 PLAN.sha256，执行阶段核对输入成员与 runner 哈希。预测器和投影代码来自未修改的历史 P4 ZIP，不使用当前工作目录中的历史代码副本。多通道删除完整继承 P4 views.project 的交叉字段清除；本次无需修补预测语义。', '',
            ('这是看到首轮先导结果后增加的有限构念检查。只扩展 cohort：纳入 CONTROLLED_CONSTRUCT 的全部 UEA/ALR/RIR/TaskSuccess 查询（该域没有 CI），不调策略、优先级、seed 或预算。235 条查询来自 36 个分支单元、9 个构念家族；与首轮有重叠，不能当作全新独立验证集。' if ref else
             '按 metric×domain 分层轮询，层内稳定 SHA-256 排序，每个 registry independence_group 至多选一条，共 240 条。保留 Full 未知与不适用，未按预测标签选样。原始 group 字段与来源见 sample.csv；唯一 group 不保证不同模板之间统计独立。'), '',
            '## 设计与估计对象', '',
            '- 机制：UEA、ALR、RIR、TaskSuccess、CI；不纳入 HIAA、Provenance 自身输出和 failure 自身输出。',
            '- 九个家族：receipt、grant、provenance、counterfactual、task_success_evidence、lifecycle、scope_lifetime、decision_reason、failure。请求/效果观察骨架与 manifest 等未删除，因此零补证预算仍可能产生点值或不适用；这不是完全无信息起点。',
            '- 两个条件：九族全缺；稳定哈希保留四族、缺五族。预算 0..9 以每条查询恢复一个家族为一单位，后者在预算 5 后已无更多家族可补。',
            '- 比较 Full、全局固定顺序、按指标固定顺序、随机顺序（8 个冻结 seed）、contract_guided。所有恢复策略在 point 或 not_applicable 时停止，终态重复到余下预算，保持公平。',
            '- guided 仅接收 metric/protocol、当前可见预测的 missing_evidence 和已获取家族；Full 与参照标签在所有选择轨迹结束后才用于评价。该限制由代码接口和阶段顺序实现，不声称是对恶意策略的操作系统隔离。',
            '- 每个家族在本查询和嵌套分支内恢复；不同查询之间不共享补证。成本是模拟的家族单位，另一指标为可见规范化 JSON 新增字节，不是线上延迟、采集费用或 token 成本。Full 行的字节成本 0 为“不适用”占位，不能参与成本排名。',
            '- 点值覆盖以全部查询为分母，N/A、unknown 单列。Full 一致率是同预测器的观察恢复一致性，独立参照 accuracy/coverage 分列，不互相替代。', '',
            '## Full 基线仍保留未知', '',
            f"Full：{fs['point_count']} point，{fs['not_applicable_count']} not_applicable，{fs['unknown_count']} unknown；点值覆盖 {fs['point_coverage']:.2%}，资格可判断覆盖 {fs['eligibility_coverage']:.2%}。", '',
            f"独立参照中可点判真值 {fs['independent_truth_n']} 条，Full 回答 {fs['independent_answered_n']} 条，正确 {fs['independent_correct_n']} 条；已答准确率 {fs['independent_selective_accuracy']:.2%}，真值子集覆盖 {fs['independent_truth_coverage']:.2%}。这不是所有 {len(qids)} 条查询的准确率，也不是通用自然语言标签准确率。", '',
            '所有恢复轨迹中，存在参照且给出确定点值的查询未出现错误；已确定资格亦未出现参照冲突。所有策略在最大预算与 Full 的状态/资格/值一致，无因删证而额外产生的、Full 不支持的确定点值。这是已运行轨迹内的检查，不是所有可能缺失模式的形式证明。', '',
            '## 主要结果', '',
            '| 缺证条件 | 策略 | 预算4点值数 | 最大预算平均实际补入家族数 | 最大预算平均新增JSON字节 |',
            '|---|---|---:|---:|---:|']
    for condition in plan['conditions']:
        for policy in ['global_fixed', 'metric_fixed', 'contract_guided']:
            b4 = indexing[condition, policy, 4]
            b9 = indexing[condition, policy, 9]
            text.append(f"| {condition} | {policy} | {b4['point_count']}/{len(qids)} | {float(b9['mean_acquired_families']):.3f} | {float(b9['mean_added_json_bytes']):.1f} |")
        r4 = next(r for r in random_summary if r['condition'] == condition and r['budget'] == 4)
        r9 = next(r for r in random_summary if r['condition'] == condition and r['budget'] == 9)
        text.append(f"| {condition} | random（8 seed均值） | {r4['point_count_mean']:.3f}/{len(qids)} | {r9['mean_acquired_families_mean']:.3f} | {r9['mean_added_json_bytes_mean']:.1f} |")
    text += ['', '随机 seed 的最小/最大值见 random_seed_summary.csv。这些是顺序随机性的范围，不是基于独立任务的置信区间。所有方法最终都达到同一 Full 终态，因此上表主要描述达到可判断结果所需的补证路径；对于 Full 自身未知的查询，补齐后仍保留未知。', '',
             'guided 与 metric_fixed 在所有预算的点值覆盖和平均家族成本相同；这不代表逐查询状态一致。个别早期预算的资格覆盖或 JSON 字节有所不同，见 guided_vs_metric_fixed.csv。P4 的 provenance 掩码会清除 counterfactual 内嵌的 source_object，但 missing_evidence 只显式记录顶层 get 的缺项，当前反馈不是完整依赖追踪；guided 可能先恢复 receipt 而错过对资格更有用的 provenance。不能据此提出“动态选择显著优于强固定策略”，也不进行结果驱动的优先级调参。新增 JSON 字节仅作成本代理的敏感性描述，本实验没有统一的字节预算控制，不能声称在公平字节预算下更优。', '',
             '## 可写入论文的主张与边界', '',
             '> 在固定指标合同和许可观察范围内，我们实现了可复算的缺证诊断与补证预算测量。离线先导显示，利用指标合同规定的证据依赖顺序，相较统一补证顺序可更早恢复部分机制判断；当前基于可见缺证反馈的动态规则未超过按指标固定顺序。对于 Full 中仍不可判断的语义和资格问题，补齐既存记录不会自动产生答案。', '',
             '本实验是测量框架的补强，不是新三值逻辑、全局最小证据算法、线上最优采集器或强防御方法。历史 CI 的语义保持、历史 ALR 的原时点原因、RIR 的污染前缀等缺口没有因本实验消失。范围仅限存量规范化观察，不对真实 harness 故障分布、采集接口可实现性、跨框架泛化作结论。', '',
             '预算、策略和 8 个随机 seed 是同一查询的重复测量，不能按结果行数扩大样本量；多请求、分支、协议和 k 的依赖也需保留。没有新增模型任务或把未人审样本标成人审。', '',
             '## 复现与文件', '',
             '在仓库根目录运行（现有冻结计划）：', '', '```bash',
             ('python experiments/evidence_recovery_pilot/reference_check.py run' if ref else 'python experiments/evidence_recovery_pilot/run.py run'),
             f'python experiments/evidence_recovery_pilot/report.py --out "{out.relative_to(pilot.ROOT)}"',
             '```', '',
             '重新 prepare 必须选一个新 --out 路径；不得覆盖已冻结计划。reference_check 的 prepare 读取首轮计划作为不调参模板。', '',
             '- PLAN.json / PLAN.sha256：冻结抽样、指标、策略、预算、输入与代码哈希。',
             '- sample.csv：每条查询来源及原始 group；query_results.csv：逐查询、预算、策略、seed 完整轨迹。发布时可能以 query_results.csv.gz 保存，gzip 解压后仍为原始 CSV；报告脚本兼容两种形式。',
             '- summary.csv / by_metric_domain.csv：总体及机制×来源分层的点值、资格、未知、Full 一致性、独立参照和成本。',
             '- random_seed_summary.csv / guided_vs_metric_fixed.csv：随机性范围与强基线对照。',
             '- RUN_STATUS.json / RESULT_AUDIT.json / analysis_errors.json：实际运行范围及完整性检查。', '']
    (out / 'README.md').write_text('\n'.join(text), encoding='utf-8')
    print(json.dumps({'report': str(out / 'README.md'), 'audit': 'PASS'}))


if __name__ == '__main__':
    main()
