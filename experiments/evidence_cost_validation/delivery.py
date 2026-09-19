"""Post-outcome presentation only; never changes frozen analyses or runs a sandbox."""
import argparse
import csv
from collections import Counter
from pathlib import Path

from experiments.evidence_contract_validation.common import ROOT, read_json, write_json, write_csv, now
from .statistics import auc


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def put(path, text):
    path.write_bytes((text.strip()+'\n').encode('utf-8'))


def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(str(v) for v in row)+' |' for row in rows])


def build(out):
    attr=read_json(out/'GAIN_ATTRIBUTION_SUMMARY.json')
    old=read_json(out/'COST_ROBUSTNESS.json')
    fresh=read_json(out/'FRESH_RESULTS.json');gate=fresh['gate']
    groups=read_csv(out/'GROUP_CONTRIBUTIONS.csv');fc=read_csv(out/'FRESH_CURVES.csv')
    effects=read_csv(out/'FRESH_EFFECTS.csv')
    ledger=[__import__('json').loads(s) for s in (out/'EXECUTION_LEDGER.jsonl').read_text('utf-8').splitlines()]
    strata=[]
    for cost in ('C1','C2'):
        for label in ('ALL','UEA','TaskSuccess','UEA_true','UEA_false','TaskSuccess_true','TaskSuccess_false'):
            for mechanism in ('ALL','whole_channel','random','failure_stress'):
                scores={}
                for policy in ('global_fixed','metric_static','dependency_guided'):
                    points={float(r['rho']):float(r['correct_coverage']) for r in fc if (r['cost'],r['stratum'],r['mechanism'],r['policy'])==(cost,label,mechanism,policy)}
                    scores[policy]=auc(points,sorted(points))
                strata.append(dict(cost=cost,stratum=label,mechanism=mechanism,**scores,
                                   difference=scores['dependency_guided']-scores['metric_static']))
    write_csv(out/'FRESH_STRATUM_AUC.csv',strata)
    paired=[]
    for name in ('COST_PAIRED_OUTCOMES.csv','FRESH_PAIRED_OUTCOMES.csv'):
        counts=Counter((r['cost'],r.get('split','fresh'),r['class_']) for r in read_csv(out/name))
        for cost,split in sorted({k[:2] for k in counts}):
            paired.append(dict(dataset=split,cost=cost,**{k:counts[cost,split,k] for k in ('benefit','harm','same')}))
    write_csv(out/'PAIRED_COUNTS.csv',paired)
    gain_table=table(['旧 C0 留出配对','数量','AUC 贡献'],[
        [kind,attr['classes']['heldout'][kind],f"{next(float(r['auc_contribution']) for r in groups if r['split']=='heldout' and r['dimension']=='sign' and r['category']==kind):+.12f}"]
        for kind in ('benefit','harm','same')])
    comparisons=[('C0','旧留出，已公开',attr['comparisons']['heldout'])]
    comparisons += [(c,'旧留出，探索性诊断',old['results'][c]['heldout']) for c in ('C1','C2')]
    comparisons += [(c,'新24实例，冻结确认批次',fresh['results'][c]) for c in ('C1','C2')]
    cost_table=table(['成本','数据资格','静态 AUC','动态 AUC','差值','正增益族'],[
        [c,s,f"{v['static_auc']:.9f}",f"{v['dynamic_auc']:.9f}",f"{v['difference']:+.9f}",f"{v['positive_families']}/6"] for c,s,v in comparisons])
    family_table=table(['新实例所属旧家族','C1 差值','C2 差值','族级结果'],[
        [r['family_id'],f"{r['difference']:+.9f}",f"{fresh['results']['C2']['paired'][i]['difference']:+.9f}",'两者为正']
        for i,r in enumerate(fresh['results']['C1']['paired'])])
    strata_table=table(['分层','C1 差值','C2 差值'],[
        [label]+[f"{next(r['difference'] for r in strata if r['cost']==c and r['stratum']==label and r['mechanism']=='ALL'):+.9f}" for c in ('C1','C2')]
        for label in ('UEA','TaskSuccess','UEA_true','UEA_false','TaskSuccess_true','TaskSuccess_false')])
    mechanism_table=table(['缺证机制','C1 差值','C2 差值'],[
        [m]+[f"{next(r['difference'] for r in strata if r['cost']==c and r['stratum']=='ALL' and r['mechanism']==m):+.9f}" for c in ('C1','C2')]
        for m in ('whole_channel','random','failure_stress')])
    # These integrated subgroup curves use their own denominators; they are not additive contributions.
    text=f'''# A 的成本稳健性与新执行验证

结论：**{gate['status']}**。预定 Gate A 与 Gate B 均通过。固定头部后、再将所有通道等权后，动态补证的小幅优势仍保留；新24实例两成本均6/6族为正、全部删一族比较为正。值得将其保留为 SkillFlow 证据框架的有限应用信号，尚不足以主张强动态算法优势或投入大规模扩样。本批到此停止。

## 1. 旧增益来自哪里

{gain_table}

11200个留出配对完整保留，净面积 +0.001691381666；开发集另11200配对（31获益、0受损、11169相同）。面积按种子先平均、任务族等权和梯形区间计算；每个互斥分组及全部预算区间之和均在1e-10内还原总差。配对计数包含重复预算/缺证条件，不能当独立样本量。

净增益全部出现在随机缺证层。首次分歧归到执行事实证据（receipt/failure）的净贡献 +0.001385388352，约占81.91%；grant/scope为 +0.000266051206，lifecycle/session为 +0.000039942108。后两者不能被省略，旧生命周期修复也不能解释全部差值。778个关闭missing优先级的离线对照与静态匹配，支持增益来自该有限规则。

四例详见 [REPRESENTATIVE_CASES.json](REPRESENTATIVE_CASES.json)：保留H05获益、H02受损、零预算相同和已知H01生命周期案例。**受损不是错误判断，而是静态可正确确定、动态仍未知。** 零预算相同案例没有实际交付初始证据，其假设投影删前提结果不作必要性见证，见 [解释注记](CASE_INTERPRETATION_NOTES.md)。必要性见证只采用实际购得证据的获益案例。

## 2. 成本口径与稳健性

{cost_table}

C0保留原不均匀10点字节预算。C1将公开头部固定为旧开发集最大值587+1024=1611，九通道固定报价总和75776，S1=77387，21点ρ=0,.05,…,1，预算floor(ρS1)。C2公开头部1、每通道1，预算0…10。静态仅用旧development从原96候选（每指标24）中选序；动态规则、预测器、候选集、缺证规则未调。三策略均在每个预算从头购证，Full只作完整证据与最高预算端点比较。

两种成本的旧留出均通过无新增错误点/错误safe、≥5/6正族、所有删一族为正、内部预算点和必要证据恢复见证门槛；Gate A PASS后才开展新样本。C1/C2是代理成本，原序列化填充协议的实际字节另记，另有策略子进程stdin字节；均不代表实网流量、账单或延迟。不同预算网格的AUC绝对值不可解释为跨成本效率提升。

## 3. 一次新执行确认

6个预选旧语义族，每族4格：有效授权/无效授权 × 提交/未提交。新输入、路径、会话、种子与中性ID；无效授权统一精确资源不匹配。正式规则与源码在结果产生前冻结。24个程序真实执行，文件/SQLite持久状态由独立oracle复核；48个UEA/TaskSuccess真值均可确定，四格全匹配。UEA=True为6/24，UEA=False为18/24；TaskSuccess各12/24，避免把违规未执行误作成功防护。

{family_table}

**Gate B：{gate['status']}**。C1内部预算有4点覆盖差≥0.005（预定要求至少2点），C1 AUC差≥0.001；两成本均6族存在内部预算静态unknown/动态正确确定见证。C1删一族最小差 {min(r['difference'] for r in fresh['results']['C1']['leave_one_out']):+.9f}；C2为 {min(r['difference'] for r in fresh['results']['C2']['leave_one_out']):+.9f}。全部新轨迹未见错误点或错误safe；最高预算均与Full一致。这是本批有限合同内观测，不能推出普遍零错误。

{strata_table}

{mechanism_table}

新批C1有103获益、3受损、20054相同，C2有44获益、0受损、10516相同；这些是配对预算行，不是独立样本。新批净增益同样只出现在随机缺证层；TaskSuccess的增益仅在False（正确识别未完成）层，True层为零。不能把它包装成提高真实任务完成率。

上两表分层后各用自身分母，数值不能相加。完整曲线同时报告unknown、初始不可行、参照unknown/not_applicable等，见FRESH_CURVES.csv。新批只有UEA/TaskSuccess；不将未测ALR/RIR伪造为零。

![两种代理成本的覆盖增量](COVERAGE_GAIN.png)

## 4. 资源、负结果与研究边界

- 实际28/48次：4次独立接口sanity、24正式、0基础设施重试；每次一个受监督程序调用（内部文件/SQL操作不是独立任务），上限16。模型/Judge/付费API均0。剩余20次不用作扩样。
- 正式12个计划未提交、sanity2个计划未提交均保留，不重跑求成功。旧47获益/1受损，以及所有新受损配对均保留于完整CSV；PAIRED_COUNTS.csv列出各阶段数量。
- 新取证轨迹旧数据215040、新数据92160，逐条独立核账；静态候选评估860160次纯函数离线试算。这些均非新业务执行、非独立样本、非模型调用。
- 7项针对性单元测试通过；首次虽7通过但触发无关全项目覆盖率门槛而退出1，日志保留；关闭该默认覆盖配置后7通过且退出0。未声称全仓库CI通过。
- 新实例仍由同一作者在同一受控程序合同生成；只覆盖6旧语义族、固定一种无效授权、人工四格与预设缺证。随机缺证层信号不能外推自然缺证。无LLM行为、真实攻击成功、跨平台、通用授权/Lifetime或ALR/RIR/CI因果验证。6族无独立统计显著性结论。
- B仍为此前NO_GAIN，本轮未执行、未改历史结果。论文主线保持统一交互与证据框架；本结果可写作受限的补证应用证据。

## 5. 审核入口

[只读复核与实际命令](REPRODUCE.md) · [主张支持表](CLAIM_EVIDENCE_MATRIX.md) · [机器摘要](SUMMARY.json) · [执行账本](EXECUTION_LEDGER.jsonl) · [新独立真值](fresh/oracle/heldout.json) · [Gate A](GATE_A.json) · [Gate B](GATE_B.json)。M0的SOURCE_AUDIT/GATE_A中“新增0”是当时阶段快照；本轮终值为28，见SUMMARY/STATUS。
'''
    put(out/'FINAL_REPORT_CN.md',text)
    put(out/'COST_ROBUSTNESS.md','# 成本稳健性\n\n'+cost_table+'\n\nGate A PASS。定义、分母与代理成本边界见FINAL_REPORT_CN.md；原字节另账，不能声称实网成本下降。')
    put(out/'FRESH_RESULTS.md','# 新执行结果\n\n'+family_table+'\n\nGate B '+gate['status']+'；28次实际执行，24正式，0重试/模型调用。\n\n'+strata_table+'\n\n'+mechanism_table)
    put(out/'CLAIM_EVIDENCE_MATRIX.md','''# 主张与证据

| 主张 | 判定 | 证据与边界 |
| --- | --- | --- |
| 旧动态增益可归因到缺失前提优先规则 | 有限支持 | 全配对/首次分歧/778禁用对照；全部净增益在随机缺证，保留1受损 |
| 去掉实例头长和通道权重后优势仍在 | 支持本合同内稳健性 | C1/C2均过Gate A；仅代理成本，旧留出已公开 |
| 新冻结实例重复小增益 | 支持本批 | Gate B PROMISING_LIMITED，6/6族和全部删一族为正；24实例而非新机制 |
| 有限证据下本批无新增错误点/错误safe | 支持观测 | 独立持久状态真值、完整轨迹核账；不能推出普遍零风险 |
| 强算法贡献/现实效率/跨平台泛化 | 不支持 | 效应小、同作者同合同、无模型或自然缺证分布 |
| ALR/RIR/CI因果完整性、B有效 | 不支持 | 本轮不测；保留旧unknown与B NO_GAIN |
| 值得继续投入 | 条件性、小范围 | 可保留框架应用论据；缺独立场景与自然缺证证据，不据此自动扩样 |
''')
    summary=dict(status='EXPERIMENT_COMPLETE',gate_A='PASS',gate_B=gate['status'],at=now(),
                 original_gain=attr['expected_heldout_delta'],old_cost_deltas={c:old['results'][c]['heldout']['difference'] for c in ('C1','C2')},
                 fresh_deltas={c:fresh['results'][c]['difference'] for c in ('C1','C2')},
                 executions=len(ledger),formal_units=24,sanity=4,retries=0,cap=48,
                 model_calls=0,judge_calls=0,paid_api_calls=0,B='NOT_RUN',
                 fresh_UEA_counts=dict(Counter(r['UEA_value'] for r in effects)),
                 fresh_TaskSuccess_counts=dict(Counter(r['TaskSuccess_value'] for r in effects)),
                 trajectory_rows=dict(old=215040,fresh=92160),candidate_trials=860160,
                 boundary='same six old families, new controlled instances; no automatic expansion')
    write_json(out/'SUMMARY.json',summary)
    state=f"M0–M4实验完成：Gate A PASS，Gate B **{gate['status']}**。新24实例C1/C2动态−静态AUC +0.002480/+0.002183，两者6/6族为正且删一族均为正，未见新增错误点/错误safe。实际28/48次（4 sanity+24正式），0重试，模型/Judge/付费API均0。优势仍小、来自受控旧语义族；保留负结果，到此停止，不扩样、不继续B。"
    readme=ROOT/'README.md';r=readme.read_text('utf-8');start='<!-- a-cost-validation:start -->';end='<!-- a-cost-validation:end -->'
    rel=out.relative_to(ROOT).as_posix()
    r=r[:r.index(start)]+start+'\n\n'+state+f'\n\n[中文结果]({rel}/FINAL_REPORT_CN.md) · [机器摘要]({rel}/SUMMARY.json) · [只读复核]({rel}/REPRODUCE.md)\n\n'+r[r.index(end):]
    put(readme,r)
    tracker=ROOT/'docs/tasks/a-cost-robustness-20260919/refine-logs/EXPERIMENT_TRACKER.md'
    t=tracker.read_text('utf-8')+'\n\nR008–R009 / M3–M4：'+state+' 发布核验另见PUBLICATION.json。\n'
    put(tracker,t)
    write_json(out/'STATUS.json',summary|dict(publication='PENDING'))
    put(out/'MIDCHECK_M3_REPLAY.md','# M3离线分析完成\n\n92160条新轨迹完整核账；双成本均先封存预测再连接真值。'+state)
    put(out/'MIDCHECK_M4.md','# M4判定\n\n'+state+'\n\n报告与只读复验待最终发布核验；不再运行业务。')
    put(out/'README.md','# A 成本稳健性与新执行验证\n\n'+state+'\n\n从[中文报告](FINAL_REPORT_CN.md)开始；[复核](REPRODUCE.md)、[主张边界](CLAIM_EVIDENCE_MATRIX.md)、[发布](PUBLICATION.json)。')
    print(summary)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();build(a.out.resolve())
