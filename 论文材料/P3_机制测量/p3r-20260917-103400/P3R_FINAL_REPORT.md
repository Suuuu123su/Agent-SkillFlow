# P3R 完整补算与有界补实验报告

状态：**P3R_EXECUTION_COMPLETE**；核心主张只获部分支持。四层结果均已落盘：历史复算、严格/敏感性口径、确定性构念、新Luna补实验。新结果没有回填旧DS失败、旧ALR原因或旧分数。

核心未识别项：历史静态pot、历史显式ALR原因、新Live严格ALR（敏感请求0/4前缀）、撤销前已采用污染控制的RIR队列，以及旧CI控制语义独立性。它们均保留为核心缺口，执行完成不表示科学主张已补齐。

## 实际完成与不能主张的结论

DS M2失败已从30条原始响应定位：29条明确输出预算截断，1条合法空选择；未重发。静态pot有真实有限域计算与独立穷举见证。61条历史ALR原数据库已核查，F严格范围[0,14/24]、G[0,6/15]，H0/22；F/G原始原因仍不能补造。RIR旧合同保留，新chain将形成、撤销、会话到达、观察和归因分开；没有已确认污染前缀时严合同仍N/A。

CI原始干预593/593追回；289对JSON内容schema被中和破坏。它是本轮新增的重要限制，数字一致不能代替中和语义有效性。T18从实际核心/Replay恢复，scripted monitor ALR2/3、RIR1 2/4、RIR3 1/2；与新9族构念一起证明测量正反例可以计算，但不证明自然模型攻击普遍成功。

## 新Live执行账目

仅gpt-5.6-luna，固定官方 https://chatgpt.com/backend-api/codex/responses ，沿用最近成功CLI传输与medium设置。实际尝试292，已结算292，未知0，在途0；usage累计502734 tokens（输入476919，输出25815）。仅Actor，新GLM/DS/Judge/防御/攻击生成均0。金额、余额未查询，不将tokens换算为实际收费。

槽位状态：{"complete": 52, "not_started": 2, "not_applicable": 6}。最多60槽，TECH未用槽不借用；各槽上限合计1104请求，外层1152，串行每批最多2，自动重试0、未知不重发。CLI原生输出上限不可设置，因此不宣称8192已被服务端强制执行。实际工具全部是本地合成文件效果，mock_send只落safe_sink。新调用以用户明确回复“授权”为依据；首次自动审核拒绝及随后直接授权原样保留，未绕过拒绝。

新ALR实际暴露请求N=0，无敏感请求前缀4/4。严格ALR Live点值N/A；构念正例不补入Live分母。

新RIR与ALR的分子、分母和未知请直接看[核心主表](P3R_METRIC_MAIN.md)及 `LIVE_RIR_COHORTS.csv`、`LIVE_ALR_SEVEN_CONDITIONS.csv`。从共享检查点真实分叉；没有脚本替Actor写污染。N只中和存储Memory的精确片段，未保留时N不适用。该设置不能识别已被共享前缀对话吸收的全部影响；confirmed-prefix仍缺证。ALR reason来自实际参考策略分支，不是模型心理解释，也不是生产Router授权。

## 输入覆盖、复算与独立核验

正式F/G/H唯一990核心+810 Replay；F+H比较630+540，无F重复计数。canary、T18 scripted/fake_reference和新Live分域。独立授权1372、图深度6495、区间468检查一致；来源集合独立重建。原始manifest精确冻结字节和记录器根/父边仍是信任边界。

`review_slice/recompute.py` 只需Python标准库，不读Key，不联网，不调用模型；相对路径切片覆盖RIR正/负/合法/N/A、ALR正/负/未知、pot 0/非0/未知、CI不稳定。它从实际文件与事件计算，非答案标签驱动。完整复算所需仓库来源另有精确定位；不声称整个历史原始仓库被压进最小切片。

## 论文使用及交付

主文优先：四格HIAA→pot定义区别→ALR严格原因缺证→RIR生命周期→UEA/来源/CI→任务失败；防御作为后部应用。可以写框架测量和证据必要性，不能写所有指标在全部模型/域都已获得严格可识别点值，也不能以缺HIAA字段断言当前Evidence完全没用SkillFlow。

逐项G01—G11见 `GAP_CLOSURE.csv` 与 `CLAIM_EVIDENCE_MATRIX.md`。历史人审仍0，P0/P1/P2未重跑，旧T19-R STOP/HOLD未恢复，P4/P5与画像路由只归档。旧文件和用户改动以基线哈希核对；没有commit/push。源码、公开消息、全部尝试结果索引、事件和本地回执保留；私有推理、CLI私有认证目录不入审查包。

入口：[核心主表](P3R_METRIC_MAIN.md)、[指标合同](METRIC_CONTRACTS_P3R.md)、[M2原始诊断](M2_DIAGNOSIS.md)、[GAP逐项表](GAP_CLOSURE.csv)、[独立切片说明](REPRODUCE.md)、[状态](P3R_STATUS.json)、[提交审查清单](COMMIT_REVIEW_LIST.md)。
