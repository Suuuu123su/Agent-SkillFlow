# T15 中文总结：OpenClaw 真实 Harness Pilot

## 结论

T15 已完成。SkillFlow 在不修改核心模型、PolicyEngine、SecurityGraph 和指标分析器的前提下，把同一组 B0、G0、M2 Scenario 同时运行在原 Mock Harness 与真实开源 OpenClaw Gateway 上。三组目标 Effect 数一致，说明统一事件边界与安全 Sink 能迁移；三组 policy 均不一致，说明 OpenClaw 并不具备 SkillFlow Mock 中等价的 Grant、来源图和撤销执行语义。

最重要的结论不是“OpenClaw 通过了安全测试”，而是：平台差异已经能被明确定位，且没有用伪造事件填补缺失钩子。本次 Pilot 不使用真实凭据、不访问用户生产配置、不执行真实外部效果，也不提供现实攻击成功率。

## 固定平台与安全边界

- OpenClaw version：`2026.8.1`
- OpenClaw commit：`452e734022214f5f00bdd44cae675cc467c3cd85`
- 运行形态：只绑定 loopback 的隔离 Gateway + OpenClaw 仓库内假 OpenAI Provider
- Tool 白名单：`read`、`write`、`skillflow_safe_sink`
- 禁止项：真实 API Key、真实网络 Sink、Shell Tool、生产 state/config、OpenClaw 核心源码修改
- 最终安全标志：`real_credentials_used=false`、`external_effects_replaced=true`、`production_state_modified=false`

## 交付内容

- `src/skillflow/pilot/`：双 Adapter 合同、Scenario 计划编译、严格事件模型、OpenClaw→`SecurityEvent` 转换、比较与报告编排。
- `integrations/openclaw/`：Gateway Driver、配置边界、假 Provider 回合脚本、进程诊断、Effect 等待和观察插件。
- `docs/openclaw-adapter-design.md`：版本 pin、钩子映射、证据强度、安全不变量、停手和回滚条件。
- `docs/evidence/t15-pilot-summary.json`：最终实跑的结构化摘要。
- `tests/unit/pilot/` 与 TypeScript tests：49 项 Python Pilot 测试和 6 项 Node/TypeScript 合同测试。

## 三场景结果

| Scenario | Mock/OpenClaw Effect | 来源结果 | 策略结果 | 定位到的平台缺口 |
|---|---:|---|---|---|
| B0 良性文件读取 | `1 / 1` | 两侧数值均 1，basis 不同 | 不匹配 | Grant matcher、Artifact provenance graph |
| G0 跨 Skill/Session Memory | `1 / 1` | 两侧数值均 1，basis 不同 | 不匹配 | Grant matcher、Artifact provenance graph |
| M2 撤销后 Memory 残留 | `2 / 2` | 两侧数值均 1，basis 不同 | 不匹配 | 上述两项、Skill revocation hook |

这里的来源结果不能写成“差值为 0”：Mock 计算全图 Artifact recall，OpenClaw 只能计算安全 Sink 上的目标 Effect 标签覆盖率。二者统计单位不同，所以正式报告固定 `provenance_basis_match=false`、`provenance_delta=null`。

OpenClaw 侧分别产生 8、38、71 条原始平台事件。G0 中观测到 4 次 Context、4 次 Skill load/invoke、1 次 Memory write、2 次 Memory read 和 1 个带 Receipt 的安全 Effect。M2 中 benchmark 有撤销事实，但固定 OpenClaw revision 没有公开的 Skill revocation enforcement hook；因此平台继续执行的事实被如实保留，没有生成伪造的 revoke 事件。

## 关键实现决定

1. 平台专用逻辑只放在 `skillflow.pilot` 和 `integrations/openclaw`，核心分析路径保持平台无关。
2. Skill invoke 必须同时满足“预注册目录已宣告”和“精确 `SKILL.md` 读取成功”；`skill_changed` 不等于调用。
3. `llm_input` 只开启 OpenClaw 明确要求的会话访问权限，插件不记录 Prompt/system prompt 正文。
4. Session key 在请求前统一小写，匹配 OpenClaw 内部规范化，避免同 Session 后续回合被拒绝。
5. Driver 在关停 Gateway 前等待每个预注册目标 Effect 同时出现 `executed=true` 和 Receipt；只有请求日志不算完成。
6. 外部效果全部改为 `skillflow_safe_sink`；Receipt 是执行证据，不是授权证据。

## 失败复现与修正

- 外部 Driver 缺少 ESM 包边界，`tsx` 曾把顶层 await 编译为 CJS 并失败；显式 `type=module` 后相同入口通过。
- OpenClaw 会把 Session key 规范化为小写；旧 Driver 的 G0 在第二个同 Session 回合稳定返回 HTTP 500，新函数小写化后四个 invocation 全部完成。
- 非内置插件读取 `llm_input` 必须显式允许 conversation access；权限收紧到这一项并以合同测试锁定。
- `after_tool_call` 异步落盘可能晚于 Gateway 关停；现在按结构化 Effect+Receipt 条件等待。
- 初版来源报告错误地对不同统计 basis 计算 `0.0`；修正后 basis 不同强制 delta 为 `null`。

## 验证摘要

- OpenClaw 完整 build：PASS。
- B0/G0/M2 真实 Gateway 双 Adapter Pilot：PASS。
- Python Pilot：49 passed；TypeScript：6 passed。
- 全量 pytest：463 passed；总分支覆盖率 90.31%，通过 90% 门槛。
- Ruff lint/format、mypy strict、静态 Schema、`skillflow doctor`、`pip check`：PASS。

## 局限与停止点

- 这不是生产 OpenClaw 安全认证，也不是现实 LLM 攻击实验。
- OpenClaw 的 Artifact provenance graph、结构化 Grant matcher、Skill revocation enforcement 仍是缺失能力；没有绕过停手条件或修改平台核心。
- 运行历史与调试日志按用户规则保留但不进入 Git；正式仓库只提交脱敏报告摘要。
- T15 是任务书最后一项。当前完成后停止，不自动接入其他 Harness、真实模型或生产环境。
