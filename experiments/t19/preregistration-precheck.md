# T19 Live 预检合同

本阶段为开发预检，不进入正式结果。8 条件（C1/C2/M2/A1 攻击，B0/N0/G0/A2 合法）× Monitor/Best Fixed/All/Evidence =32 条完整链，按 matrix-precheck.json 顺序执行。Best Fixed=T，来自120条件开发枚举及8条技术修复。

模型 deepseek-v4-flash；端点 https://api.deepseek.com/responses。沿用 T17 已验证服务配置：推理 medium（DS服务映射 high）、不发送 temperature、2048输出 token、automatic cache、串行。请求载荷最大12000字节，完整任务链16次调用，Session和恢复不重置；自动重试为0。凭据只在可信宿主和固定子进程内存，通过匿名管道传递。副作用全部 Safe Sink 合成数据。

模型 refusal/no-call/schema/任务失败保存为原样结果，不择优重采。请求前 input_bytes/agent_turns 超限单列；网关、用量不明、冻结漂移、绑定失败保留现场并停止该尝试。未知费用保守预留；未经本地核对不重发。每链最坏费用0.03662848美元，32链最坏1.17211136美元，纳入本轮35美元累计上限。

动态组件与正常任务数据合同保持共享；正式阶段不得参考预检结果选择正式样本。预检允许修复接口错误，但原记录不覆盖，新增技术验证单列。完整正式阶段另行冻结指标及补证合同。
