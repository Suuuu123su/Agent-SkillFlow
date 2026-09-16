# P2修订：Luna同组件库All＋本地实时进度

这份包**完整替代**上一版GLM默认的P2任务，不需要两份Goal一起执行。修订原因是用户明确表示GLM额度耗尽，并要求简单HTML实时进度页。

## 不变与改变

|项目|本轮要求|
|---|---|
|实验|P2：All-SameLibrary，只有新增All|
|新请求模型|gpt-5.6-luna；Actor、必要语义提取、Content、Derived、Judge均不能调用GLM|
|组件参考|实际Luna Evidence v3的冻结组件与合并/恢复，**不是GLM dynamic2**|
|规模|39正式（26攻击＋13正常）＋最多4TECH；总43目标阶段|
|其他|P0保持结项；P1继续延期；Evidence/NoDefense/Content-only/Derived-only/TaskShield新增0|
|页面|真实记录驱动、只读、2秒刷新、不调用模型、仅127.0.0.1|
|结果|新All单独报告；历史Evidence按实际合同与Judge兼容性分层，不强行拼公平排名|

先读`01_CODEX_GOAL.md`、`02_PROTOCOL_AND_EXAMPLES.md`，再读`03_DASHBOARD_INTEGRATION.md`。`monitor/`提供可接入的轻量页面、投影写入器和本地服务器；尚未连接本地实验，初始页面不会伪造运行进度。

`TASK_KEYS39.json`只保留上轮39个原生任务键，**已移除GLM的观测ID与轨迹哈希**。本地必须从Luna结果重建引用，不能把O-0157等GLM记录换个模型名继续使用。

## 启动页面

在任务包目录运行（实际状态文件应由本地runner写入）：

```powershell
python -B monitor/serve_progress.py --status-file 'E:\Skill ＆ Harness\Agent\runs\p2-luna-all\public\progress.json' --port 8765
```

浏览器访问控制台打印的本机地址。端口占用则选另一空闲端口并记录，不终止别人的进程。服务器不提供实验启动、暂停、重跑接口。

本包只生成了任务与网页代码；不包含已运行的All成绩。GitHub旧任务入口由本地Codex按本次修订更新，不宣称本次对话已经推送。
