# T17 Final Summary

**最终结论：INCOMPLETE，不得标记 T17 完成。**

| 阶段 | 状态 | 结论 |
|---|---|---|
| T17-A | measured | 基线审计与 Evidence Domain 冻结完成 |
| T17-B | measured | Reference Harness 与受信 Runtime 合同完成 |
| T17-C | measured | 24 core 变体与 18 replay 规格完成 |
| T17-D | measured | Scripted Golden 24/24 core、18/18 replay 通过 |
| T17-E | incomplete | Live Canary scheduled 分母未闭合 |
| T17-F | not_available | 未运行 |
| T17-G | not_available | 未运行 |
| T17-H | not_available | 未运行 |

## 已测核心结果

Scripted Golden：

- TSR：20/24 = 0.833333
- Safe TSR：11/24 = 0.458333
- Verified Target Effect：15/24 = 0.625
- TaskSuccessEvidence / Receipt / Hook coverage：24/24、54/54、89/89
- UEA count / type / weight：8 / 7 / 8
- Provenance TP/FP/FN：250 / 0 / 12
- Precision / Recall / F1：1.0 / 0.954198 / 0.9765625
- HIAA C1/C2：1.0 / 1.0
- ALR、RIR(1)、RIR(3)：0.5、0.5、0.5
- Replay CI negative/zero/positive：0 / 9 / 9
- 24 个 core 的 5 次指纹一致性：24/24

Live Canary Partial：

- 最新 Attempt：16/24 core、12/18 replay 完成；另 1 core 有完整用量但无终态
- observed-only TSR：12/16 = 0.75；正式 scheduled value 为 null
- observed-only Safe TSR：7/16 = 0.4375；正式 scheduled value 为 null
- Model refusal：0；Benign task failure：1
- 累计 API 请求/响应：182 / 181
- Input / cached / visible output / reasoning token：26,253 / 0 / 6,319 / 15,902
- 实际费用估算：$0.0319158
- 保守占用：$0.0328657

## 状态边界

Scripted、不同 Live Attempt 和未运行阶段不做 micro 聚合。T17-E 的 Wilson 区间保持 incomplete；Canary cluster bootstrap 为 not_applicable。Model1 正式、Model2、跨模型和 Defense 指标均为 not_available。

## 产物

- docs/evidence/t17-final-metrics.json
- docs/evidence/t17-final-summary.csv
- docs/evidence/t17-e-canary-partial-audit.json
- docs/summaries/T17E_Summary.md
- docs/summaries/T17F_Summary.md
- docs/summaries/T17G_Summary.md
- docs/summaries/T17H_Summary.md

完整 Raw 保留在 runs/t17-live-20260902-01 至 runs/t17-live-20260902-05，本地不改写、不合并、不删除。
