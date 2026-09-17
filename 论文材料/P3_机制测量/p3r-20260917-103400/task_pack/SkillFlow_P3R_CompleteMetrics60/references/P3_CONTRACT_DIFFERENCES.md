# 原合同与可恢复语义的差异

|项目|原实现/保存事实|更严格或理论口径|本轮处理|
|---|---|---|---|
|HIAA_run|同selector四格有回执Effect；可授权|不能泛指UEA或Evidence−All ASR|两种风险量分开；结构控制通过，未验证私有文本语义|
|HIAA_pot|aggregate_hiaa._reachable 枚举观测未授权执行类型|静态完整可达集合 W(U_H1\U_H0)|原观测集合值0可复算；静态版缺完整能力集合|
|ALR reason|T17-v2依据保存baseline/config/basis推导|T11.1输入要求原BaselineReason，显式保存字段缺失|历史算法可用但标版本；严格版缺证，不由Judge补写|
|ALR 中和|同checkpoint identity/neutral；原core另存|不能假装三个独立随机臂|逐分支身份保留；不补采|
|RIR队列|task-success条件分母13或0|有效污染前缀等更严格队列|保留原分母；prefix confirmed 为unknown|
|RIR归因|正selector CI + revoked主体撤销前来源 + 后续未授权Effect|逐对象INFLUENCE_CONFIRMED/独立GT_influence|只按原v2解释，不把GT_data单独当因果|
|CI有效性|结构有效的identity-neutral分支|identity复现原核心稳定性更严|原结果保留；F/G 5/16不稳定对单列|
|UEA权重|每实际未授权操作1|sensitivity不是该主权重|首次独立核对误用已定向修正；原报告未改|
|Provenance|受控Oracle成员关系，按图深度分层|自由语言精确因果真值/独立图算法|前者有数；后者不宣称已验证|
|T18四格|task_contract.risk_selectors；冻结matrix含多种防御模式|不能直接读取为空的T17 metadata.harm_selector|定向绑定其自有22组matrix；不混Live|

原合同入口：`docs/summaries/T11_Summary.md`、`docs/summaries/T11.1_Summary.md`，及 METRIC_CONTRACTS.json 的逐文件哈希。代码复算成功不意味着上述研究语义缺口消失。
