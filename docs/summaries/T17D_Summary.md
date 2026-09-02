# T17-D 总结：Scripted Golden 全指标重跑

- 状态：PASSED
- 正式根：runs/t17-scripted-20260902-02
- 核心 Run：24/24
- Replay pair：18/18
- 确定性：24/24 配置均 5/5 指纹一致
- API 调用：0

## 主要结果

| 指标 | 结果 |
|---|---:|
| Task Success Rate | 20/24 = 0.8333 |
| Safe Task Success Rate | 11/24 = 0.4583 |
| Verified Target Effect Rate | 15/24 = 0.6250 |
| TaskSuccessEvidence coverage | 24/24 = 1.0000 |
| Receipt coverage | 54/54 = 1.0000 |
| required Hook coverage | 89/89 = 1.0000 |
| UEA count / type / weight | 8 / 7 / 8.0 |
| Provenance TP / FP / FN | 250 / 0 / 12 |
| Provenance Precision / Recall / F1 | 1.0000 / 0.9542 / 0.9766 |
| C1 HIAA_run / HIAA_pot | 1.0 / 0.0 |
| C2 HIAA_run / HIAA_pot | 1.0 / 0.0 |
| ALR | 1/2 = 0.5 |
| RIR(1) | 1/2 = 0.5 |
| RIR(3) | 1/2 = 0.5 |
| Replay CI | -1: 0，0: 9，+1: 9 |

Task/Safe Task 结果来自独立的 experiments/t17/scripted_golden.yaml，不从被测报告
反推。风险与任务结果由标准 RunRiskReport、ReplayRiskReport 和
ExperimentRiskReport 重建；未使用模型输出作为 Ground Truth，也未按自身最大值
归一化。

Experiment manifest SHA-256：
a12659ffb0f5b3a730dbff04aa971e46ab0cab4afbb5fbdfd39ef463f477181c。

Experiment report SHA-256：
a1084ecdda5d6d040abc905e9e735c584deae4abf2bb6055b07a653007e3a0c2。

结构化汇总：docs/evidence/t17-scripted-golden-summary-v2.json。

runs/t17-scripted-20260902-01 与
docs/evidence/t17-scripted-golden-summary.json 是被审查否定的早期 Attempt：
它把部分覆盖率按实现输出自归一化，不能作为正式 T17-D 证据。该 Attempt 只在本地
保留，不删除、不合并，也不进入正式分母。

## 质量门

- 修正前全量基线：873 passed，分支覆盖率 90.03%；
- 证据绑定修正后的 T17/T16 定向回归：45/45 测试通过；该定向集合因全仓
  coverage 门产生非零退出码，不是功能测试失败；
- 当前 strict mypy：315 source files，无错误；
- 当前 Ruff lint：src 与 tests 通过；
- pip check：通过；
- doctor：Python、SQLite、依赖与 E 盘临时目录全部通过；
- T17 凭据模式扫描：0 命中。

依照用户后续指示，证据修正后未重复执行全量 pytest。上述结果验证框架和合成
Oracle 的机械闭环，不是现实 LLM 攻击成功率。
