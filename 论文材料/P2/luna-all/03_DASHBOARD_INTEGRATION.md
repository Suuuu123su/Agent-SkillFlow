# 实时页面接线（不依赖额外包）

## 文件职责

- `monitor/index.html`、`style.css`、`app.js`：简单中文只读页面；2秒轮询。
- `monitor/progress_writer.py`：从runner提供的最小白名单快照计算统计并原子写JSON；没有SDK或模型调用。
- `monitor/serve_progress.py`：只监听127.0.0.1；路径白名单，不是全目录文件服务器。
- `monitor/progress.not_connected.json`：初始未连接状态，不是演示成绩。
- `tests/test_monitor.py`：无模型单元测试；模拟计数仅在临时测试目录。

## 推荐接法

由现有可信runner/账本适配器组装最小状态，**不要把整个ledger或完整工具返回直接放入JSON**：

```python
from progress_writer import write_snapshot
# root位于本轮public目录，不能位于被测workspace内。
# units来自当前run真实槽位/状态；旧历史Evidence不计入新运行进度。
write_snapshot(public_dir / 'progress.json', {
    'run_id': run_id, 'state': actual_run_state,
    'phase': actual_phase, 'model': 'gpt-5.6-luna',
    'transport': frozen_transport,
    'started_at': run_started_at,
    'heartbeat_at': runner_heartbeat_at,
    'last_event_at': latest_real_event_at,
    'current': current_whitelisted_slot_and_role,
    'requests': ledger_counters,
    'units': current_run_public_units,
    'events': last_12_safe_event_codes,
})
```

事件写入后立即刷新；runner自身定时最多5秒更新心跳。独立web服务器不刷新heartbeat_at、不调用模型、不根据时钟增加完成数。写入器不是调度账本，重启须从真实账本恢复再投影，不能以网页JSON恢复模型请求。

`units`：每条含 `unit_id, eval_id, phase (CORE/TECH), attack (bool/null), status, verdict, actor_turn, error_code, reference_match`。

`status`取值：`not_started / running / awaiting_judge / complete / technical_error / response_unknown / blocked`。

`verdict`仅能是 `compromised / partial / safe / null`；`complete`表示已保存有效原生判词，Actor正常结束但未判分为`awaiting_judge`。若技术终态后仍存在有效原生判词，保留status及verdict，页面同时显示，不把Safe自动解释为业务完成。

`requests`为本阶段累积实际请求：`attempts, settled, in_flight, response_unknown`。满足后三者之和等于attempts；发送前纯本地异常不计已发请求，单列unit技术状态。另可给`actor, semantic, content, derived, judge`分类计数；缺失不能冒填真实用量。

`current.role`取`actor/semantic/content/derived/judge/idle`；禁止原始model prompt/error message。`events`只接受时间与固定code，例如`UNIT_STARTED`、`REQUEST_SETTLED`、`JUDGE_DONE`。详细原因保留在本地受控报告，不上网页。

## 页面状态

run state可为`NOT_CONNECTED, READY, RUNNING, PAUSED, BLOCKED, COMPLETED, COMPLETED_WITH_GAPS, STOPPED`。当前未接线只显示NOT_CONNECTED。COMPLETE状态不能由网页根据进度自动决定；由runner按实际账本给出。

统计分开：
1. 正式执行终态数/39（包括已结算技术错误与响应未知，不代表成功）；
2. 有效判词数/39；
3. 已启动、等待判分、未知/错误、未启动；
4. TECH已登记/4以及终态数；
5. 攻击C/P/S、已判分n/26；正常Safe/已判分n，计划13；
6. 本次真实请求数，不混入HTTP网页轮询。

如果尚无该层判分，显示横线。心跳30秒未更新提示陈旧，仍保留最后一次快照；这不是自动结束/重发条件。历史兼容性单列，不把GLM引用当Luna。

## 本地启动与检查

```powershell
python -B -m unittest discover -s tests -p 'test_monitor.py' -v
python -B monitor/serve_progress.py --status-file '<本轮public目录>\progress.json' --port 8765
```

服务器打印实际URL，Codex可以用正常浏览器打开。该工具不执行研究任务；正式runner必须另外按Goal启动。端口占用时换端口，不杀其他进程。服务器只返回自身页面资产和该状态文件的白名单投影；POST/任意文件/目录遍历不支持。

网页与数值聚合故障优先独立修复，不改变Actor/防御判定或重跑正式样本。无真实记录时，不使用随机数、假进度或“演示完成”填充界面。
