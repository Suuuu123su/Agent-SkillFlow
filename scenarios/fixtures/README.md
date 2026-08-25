# T12 固定 Fixture 目录

本目录记录 T12 场景库的固定 Skill、资产、Canary 与能力匹配中性内容。它是可审计目录，不是任意代码加载入口。

- Skill 实现只允许 `fixture://t12/...`，对应的封闭注册表位于 `src/skillflow/benchmark/t12_fixtures.py`。
- `catalog.yaml` 固定每个资产或中性内容的 UTF-8 长度与 SHA-256；场景测试会检查目录、Scenario 内联 marker 与 Canary 摘要一致，防止副本漂移。
- 运行时仅把已校验 Scenario 的 marker 写入该 Run 独占的临时 workspace；Skill 和 Tool 不读取本仓库路径，也不能访问宿主文件。
- 网络动作只写 `mock://` 进程内 Sink；本组 Fixture 不注册 Shell 动作、动态导入、模板执行或真实网络客户端。
- Replay 的 identity/neutral 派生仍由 T10 的结构保持中和器在隔离分支内生成，不从本目录读取答案。
