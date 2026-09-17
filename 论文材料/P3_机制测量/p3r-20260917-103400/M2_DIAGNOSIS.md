# DS M2 原始失败诊断

全部30条的首次阻断均发生在 m2-a-read。原请求的结构化输出合同要求 selected_action_ids 和 output_text；tools 数组为空，因为旧协议是动作ID选择器而非原生工具参数调用。29条原响应明确保存 incomplete_details.reason=max_output_tokens，且没有可见决策输出。另1条 s04-r1 目标样本返回合法空选择，明确说明当前动作列表不含整个任务的撤销与后续会话读取；这是局部步骤与全局任务的解释不一致，不是截断。不是根据缺Memory猜测截断。

源文件存在于宿主workspace；m2-source应由模型选择read-memory-source后，真实file.read工具产出并绑定。空决策导致该工具未执行，随后m2-a-write因missing_input被跳过。不能把下游missing_input误记为最早根因。29条没有可机械修复的JSON；另1条合法空选择也不能强改为调用，故不能离线补写历史Memory。F正例的真实读/写动作单独封存。

新入口改用真实工具调用循环、明确读写参数与可见工具结果，继承最近成功Luna传输，不套用旧DS 2048输出设置。旧G的30/30 Memory未形成与RIR空分母继续保留；没有重发任何旧请求。
