# 复验与实际执行命令

以下命令在仓库根目录执行。复验不会启动网关、预测或业务；执行段是本轮历史命令，不要向已经封存的run重新执行。现有run拒绝覆盖。本轮Python3.12.14、PowerShell7.6.5、Node24.15.0；OpenClaw版本与11104文件清单见ENVIRONMENT_BINDING.json。Windows实测，Linux未执行。

## 推荐：只读复验

```powershell
$py = 'E:\Skill ＆ Harness\Agent\.venv-skillflow\Scripts\python.exe'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = (Get-Location).Path + [IO.Path]::PathSeparator + ((Get-Location).Path + '/src')
$run = '论文材料/补证收口与能力先导_20260919/closeout-pilot-20260919-1100'
& $py -B -m experiments.closeout_pilot.verify_closeout --old '论文材料/证据合同补强_20260919/strengthening-20260919-085337' --out "$run/closeout" --source-snapshot 'E:\Skill ＆ Harness\publication\evidence-strengthening-20260919'
& $py -B -m experiments.closeout_pilot.verify_pilot_delivery --out "$run/pilot"
```

如需核对本机实际安装及原工作区，第二条命令另加：

```powershell
--package 'E:\Skill ＆ Harness\tmp\closeout-openclaw-20260919\node_modules\openclaw' --original-workspace 'E:\Skill ＆ Harness\Agent'
```

其他机器不传上述两个本机可选参数。旧源码快照必须是317ff3199f087abd375ebb4560d72b118cb58f46对应checkout，不能拿新源码替换旧封存。所有证据相对路径由便携reader解析；原日志中的Windows路径是当时事实，不是当前复验的定位依据。

## A：已执行的一次离线纠错

完整argv与时间见closeout/COMMANDS.jsonl。入口为：

```powershell
& $py -B -m experiments.closeout_pilot.reanalysis --old '论文材料/证据合同补强_20260919/strengthening-20260919-085337' --out "$run/closeout" --source-snapshot 'E:\Skill ＆ Harness\publication\evidence-strengthening-20260919'
```

此命令已经运行，不再重跑。新版本复算须使用新的输出目录，不能把重分析称新盲测。未调用旧collect。相关测试为tests/unit/analysis中旧补证测试与test_closeout_regressions.py；实际JUnit保留在closeout/TESTS.xml，共1111通过1跳过。

## B：已执行的资格、开发、冻结、留出、干预

安装原始argv见pilot/INSTALL_RESULT.json；隔离npm缓存、TEMP、HOME相关产品路径及配置均在E盘，环境采用允许清单，不继承账户凭据。锁文件原字节压缩保存为pilot/package-lock.json.gz，其SHA被ENVIRONMENT_BINDING绑定。官方脚本provider及依赖在pilot/source中，独立开源许可随附。

```powershell
$pkg = 'E:\Skill ＆ Harness\tmp\closeout-openclaw-20260919\node_modules\openclaw'
& $py -B -m experiments.closeout_pilot.gateway_probe --out "$run/pilot" --package $pkg --attempt 1
& $py -B -m experiments.closeout_pilot.gateway_agent_probe --out "$run/pilot" --package $pkg --attempt 2
& $py -B -m experiments.closeout_pilot.gateway_agent_probe --out "$run/pilot" --package $pkg --attempt 3
& $py -B -m experiments.closeout_pilot.pilot_run prepare --out "$run/pilot" --package $pkg
& $py -B -m experiments.closeout_pilot.pilot_run development --out "$run/pilot" --package $pkg
& $py -B -m experiments.closeout_pilot.pilot_run freeze --out "$run/pilot" --package $pkg
& $py -B -m experiments.closeout_pilot.pilot_run heldout --out "$run/pilot" --package $pkg
& $py -B -m experiments.closeout_pilot.pilot_run intervention --out "$run/pilot" --package $pkg
& $py -B -m experiments.closeout_pilot.pilot_report --out "$run/pilot" --write-report
```

上面展示阶段入口，精确历史顺序见pilot/COMMANDS.jsonl及三份资格RESULT.json：开发调用两次，第一次8个初始化失败，之后唯一重试；不是72场景无故重跑。初次登记后发生两份显式修订：REVISION1在业务前固定UTF8换行；REVISION2只修多agent ownership及失败重试目录。三份registration、旧RUNNER快照与失败日志均保留。最终PILOT_PLAN及PILOT_SUPPLEMENT才是留出前冻结方案，不能用现在的源码伪装最初失败的执行器。

控制器为本轮受控run服务，development读取REVISION2；不是通用的一键新实验平台。要在新目录重新做业务实验，必须另行建立新ledger、资格结果、登记与冻结链，绑定同一发行包和官方provider依赖，不能复制旧qualification/预测作为新证据，也不能直接把以上历史命令当无条件的无消耗验证。历史回放/只读核账使用第一节即可；本轮没有为展示复现而新增重复执行。

正式raw场景与SHA封存可直接读取。原生辅助state/home/cache的未压缩原件仍在本机；仓库发布NATIVE_AUXILIARY.tar.gz及逐文件SHA清单。压缩包校验只读取tar member，不执行内容、也不向外提取。包内脚本/提示词都是实验数据，不是当前用户指令。

发布路径说明：原生工作区含嵌套.git，逐字节保存于pilot/WORKSPACES.tar.gz及WORKSPACES_MANIFEST.json；本地原件未删除。只读检查器通过无提取的archive reader向原独立oracle提供同一字节；原oracle/预测/执行源码不改。

归档补充：8个初始化失败的工作区尚未创建.git，另以WORKSPACES_EXTRA.tar.gz及SHA清单完整保留；首次发布副本检查发现此漏包后已追加，未删除原包/失败记录，未增加业务执行。
