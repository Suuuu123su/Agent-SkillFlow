# P4解释修订（原字段和结果不变）

## 1. 来源自身依赖与跨指标影响分开

| raw_metric | 点值损失 | 关系 |
|---|---|---|
| ALR | 87 | downstream |
| Provenance | 7472 | self |
| RIR | 14 | downstream |
| CI | 593 | downstream |

核对式：8166 = 7472 + 87 + 593 + 14；自身占比7472/8166=91.50%，下游共694条。ALR的87按查询合同计数，并非87个独立请求；CI的593和RIR的14也不能与来源成员当同单位比较。不得用总损失排序“证据最重要”。完整分母/转移见[tables/self_vs_downstream.csv](tables/self_vs_downstream.csv)。

## 2. ALR严格合同与旧推导reason分开

| 阶段 | 原protocol | N | 真 | 假 | 未知 | 缺证识别界 |
|---|---|---|---|---|---|---|
| f | T11_explicit_reason | 24 | 0 | 9 | 15 | [0,15/24] |
| f | P3R_identity_guard | 24 | 0 | 10 | 14 | [0,14/24] |
| g | T11_explicit_reason | 15 | 0 | 5 | 10 | [0,10/15] |
| g | P3R_identity_guard | 15 | 0 | 9 | 6 | [0,6/15] |
| h | T11_explicit_reason | 22 | 0 | 22 | 0 | [0,0/22] |
| h | P3R_identity_guard | 22 | 0 | 22 | 0 | [0,0/22] |

T11_explicit_reason的第5项只要求原请求实际Effect/Receipt；P3R_identity_guard另要求identity相同参数请求执行。它们不是同一个合同。F旧14/24、G旧6/15为T17推导reason版本的点值，仍作为历史结果保留。严格上界恰与旧点值相等时，也不能把范围改写为确定点值。更强合取增加已知false，只改变该合同下的可辨识结论，不是同一风险下降。

## 3. P4 E_STS只加显示别名

`raw_metric=E_STS`、`protocol=U_and_not_verified_contract_violation`保持原样；正文显示 **STS_target_contract**。本合同为U AND NOT receipted risk-selector endpoint。P0辅助E_STS显示E_STS_posthoc(P0)，依赖其实际业务违规V与辅助标签；本轮不重标、不合并分母。UEA单独要求实际Effect/Receipt和授权事实，V不改名UEA，也不新算“授权版STS”。

## 4. 额外发现的版本分母冲突

F和H的c2-tool-return-grid/valid_only，P3R保存四格各13，P4保存四格各15；两者点值均1。表A保留P3R，表B保留P4。scheduled四格各15不受该差异影响。本轮仅证实保存分母差异，未重新裁定资格算法或执行原始事实复算。详见[NUMERIC_CONFLICTS.csv](NUMERIC_CONFLICTS.csv)。
