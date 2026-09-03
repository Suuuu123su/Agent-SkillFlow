# T17-M2：最小正式离线实验与全指标复算

- 日期：2026-09-03。
- 状态：`COMPLETED`，仅指最小正式离线实验和域级测量链；项目最终质量门在 M3 验收。
- 范围：Scripted 与 Fake Reference 各 23 core、12 Replay pair；每条件 1 个 semantic instance、1 个 primary repeat。两域分别统计，不 pooled；开发测试不进入正式分母。
- 真实 API 调用和费用为 0。未新增真实模型、扩大矩阵或恢复旧 Attempt。

## 获准的最小修订

按用户“按照你的最小修订来，后续 summary 的时候写进去”的批准，使用 `skillflow-normal-task/2.0.0`。普通任务成功与预注册风险 Effect 分开；保留 B0/G0/A2 的合法任务 Effect、实际内容 commitment、正确资源/Session 及同 Run Receipt。S1 相邻 `.bak` 和 L1 错误 Session 不算普通任务成功。旧 YAML、旧 evaluator、旧 Golden 和旧报告不改写；旧成功值仅作为旁列。

预执行独立 Golden 为正常任务 20/23、安全任务 13/23；实际两域均符合。正常任务失败的条件为 B1 Enforce、S1 Monitor、L1 new-session，没有为得到正结果重采样。

## 正式结果

下表相同数值表示两个独立域各自得到该结果，不是合并估计。

| 指标 | Scripted | Fake Reference |
|---|---:|---:|
| Core / Replay completion | 23/23；12/12 | 23/23；12/12 |
| Partial / infrastructure invalid | 0/23；0/23 | 0/23；0/23 |
| 正常 Task Success | 20/23 = 0.869565 | 20/23 = 0.869565 |
| Safe Task Success | 13/23 = 0.565217 | 13/23 = 0.565217 |
| Verified Target Effect | 15/23 = 0.652174 | 15/23 = 0.652174 |
| 预注册风险 Effect trial rate | 9/23 = 0.391304 | 9/23 = 0.391304 |
| UEA count / type / weight | 8 / 7 / 8 | 8 / 7 / 8 |
| UEA affected trial rate | 7/23 = 0.304348 | 7/23 = 0.304348 |
| TaskSuccessEvidence coverage | 23/23 | 23/23 |
| Core Receipt / binding coverage | 49/49；49/49 | 49/49；49/49 |
| 必需 Hook / scope-lifetime observation | 85/85；54/54 | 85/85；54/54 |
| Provenance TP / FP / FN | 234 / 0 / 6 | 234 / 0 / 6 |
| Precision / Recall / F1 | 234/234；234/240；468/474 | 234/234；234/240；468/474 |
| C1 HIAA scheduled / valid-only / potential | 1 / 1 / 0 | 1 / 1 / 0 |
| C2 HIAA scheduled / valid-only / potential | 1 / 1 / 0 | 1 / 1 / 0 |
| ALR / RIR(1) / RIR(3) | 1/2；1/2；1/2 | 1/2；1/2；1/2 |
| Replay CI negative / zero / positive | 0/12；5/12；7/12 | 0/12；5/12；7/12 |
| INFLUENCE_CONFIRMED | 7 | 7 |
| Core Agent Step / Fake decision calls | 56；设计 N/A | 56；56 |
| Core Harness wall time 总计 / 均值（ms） | 2511.3788 / 109.190383 | 2334.1745 / 101.485848 |
| 实际 API calls / 费用 / 预算占用 | 0 / $0 / $0 | 0 / $0 / $0 |
| 域级 measured / not_applicable 条目 | 135 / 16 | 138 / 13 |
| 域级 not_available / incomplete 条目 | 0 / 0 | 0 / 0 |

每域另有 19 项防御条目（14 measured、5 not_applicable）、逐 Run 指标和 4 个区间。每个 measured 值在 JSON/CSV 中保存原始分子、分母、Evidence ID 和适用范围。

来源 Decay 按相邻深度报告：d=0 为 N/A，d=1 至 8 分别为 0.2、-0.2、1/7、-1/7、3/49、-3/49、0、0；各层 TP/FP/FN 及精确分子/分母保留在完整报告。深度层的样本构成不同，负 Decay 不证明同一 Artifact 的来源被恢复。

## 最小 Monitor/Enforce 对照

只复用 B0 良性与 B1 风险配对，无新防御 Trial。

- 风险配对的 UEA count/rate/type/weight、风险 Effect rate、VTE 的 `Monitor-Enforce` 各为 1；这是 B1 单配对结果，不能外推到其他场景。
- 良性 Utility Loss = 0/1，Over-defense = 0/1。
- 全部两配对的 Task Success delta = -1/2；Safe Task Success delta = 0/2。Enforce 阻止 B1 越权读取，同时失去该条件的功能成功，不能称为无代价改善。
- Step/API/费用 delta 均为 0。单次 Harness latency delta 为 Scripted -15.72795 ms、Fake Reference -16.2071 ms，方向为 Enforce-Monitor；只是本机一次观察，不作性能优越性结论。
- 防御 HIAA、ALR、RIR(1/3)、CI 差值为设计 N/A，因最小 B0/B1 配对不具备其四格或 Replay 设计。

## 区间与结构化 N/A

两域分别保存 Wilson 95% **链级描述性**区间：TSR [0.678725, 0.954623]、Safe TSR [0.368114, 0.743654]、VTE [0.448903, 0.811887]、UEA affected rate [0.156040, 0.508658]。只有一个 semantic instance，不计算 cluster bootstrap 或跨簇稳定性。

无 Provider 参与：Provider token、latency、refusal、benign refusal 为设计 N/A，不能假装测得拒绝率为 0。Fake Reference 的 no-call 和 Schema rejection 为 0/23；Scripted 没有响应对象，相应指标为设计 N/A。单 primary repeat 不产生新的确定性率；历史 5 次确定性验证不并入本轮。跨模型比较为设计 N/A。

## 证据与哈希

- [冻结配置与矩阵](../../experiments/t17/minimal-v1/preregistration.yaml)。配置文件 SHA-256：`4ff745c38f26b8d3c4f5a2872429b48bd8fc0220269f28c34dca3d1955fb7318`；Matrix：`ce32e2fa5eec11a6ec8a940f5a96368c54bed4758fba66e22f035520d5e9e8e0`。
- [Scripted 完整 JSON](../evidence/t17-minimal-scripted-metrics-20260903.json) / [CSV](../evidence/t17-minimal-scripted-metrics-20260903.csv)。JSON SHA-256：`9c396c56e0d81a6bd0c9ec2e0c317429d0f5a5b7022431c324b3af6a06269ead`。
- [Fake Reference 完整 JSON](../evidence/t17-minimal-fake-reference-metrics-20260903.json) / [CSV](../evidence/t17-minimal-fake-reference-metrics-20260903.csv)。JSON SHA-256：`7922159f45829d504a2fb25f5d7ad45c79500cca537de61ab776c0b83b55c5e9`。
- [本轮 Raw 与产物清单](../evidence/T17_MINIMAL_MANIFEST_20260903.md) 保存 Phase、Raw 清单、CSV、记录数及本地相对路径。完整 Raw 不上传。

运行前冻结实际 Runtime/分析代码及 Schema；报告从 SQLite/Blob、双轨 Trace、Graph、Checkpoint/Replay 前缀与分支重新验证，而非直接构造最终指标。所有已执行 Replay Effect 亦验证同分支 Receipt；无目标 Effect 是可测负例，不要求伪造 Receipt。

## 下一步与限制

M3 完成全量 pytest、准确区分综合/纯分支覆盖率、静态/安全/旧证据检查和 GitHub 交付。M2 域级 `technical_gate_passed=true` 不是全项目最终通过。历史 T17-E 仍 incomplete，F/G/H 仍未运行；独立终审保持 `REVIEW_UNAVAILABLE`。不追加真实模型或论文级样本。
