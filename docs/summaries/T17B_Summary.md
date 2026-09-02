# T17-B 总结：Reference Harness 与可信 Hook

- 状态：PASSED（零费用技术门）
- API 调用：0
- 外部 Effect：全部为本地 Safe Sink / Mock Receipt

LiveReferenceHarnessAdapter 保持原 HarnessAdapter 与
CheckpointableHarnessAdapter 合同不变，只替换 Skill 决策后端。模型只能选择当前
FixtureScript 中预注册的 action_id；Tool 参数、Artifact ID、Grant、origin、
decision basis、Effect 与 Receipt 仍由受信 Runtime 生成。

ReferenceModelDecision 使用 extra=forbid。模型提交未注册 action、重复 action、
origin_ids 或 grant_id 时会被拒绝。Reference Observation 从 EventStore 与真实
Receipt 机械投影 Authorization、Decision Basis、Provenance、Effect、Revocation
与 Task Success；executed Effect 缺少 Receipt 时绑定检查失败。

Fake Reference Model 已通过：

- B0 完整 Runtime/Policy/Grant/Effect/Receipt 集成；
- checkpoint/restore 回归；
- 24 core + 18 Replay 的完整 Matrix/Replay 技术运行；
- 缺失 Receipt 与伪造证据负向测试；
- 新路径未导入 socket、subprocess、requests、httpx 或 keyring。

本阶段证明 Hook 接口与受信边界可运行，不是现实平台 Hook 结论。

