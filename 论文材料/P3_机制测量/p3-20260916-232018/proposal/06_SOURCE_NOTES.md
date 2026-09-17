# 来源与本包核验范围

## S1：用户当前提供的v2主线与计划

`references/`中保存本轮实际挂载文件的原字节副本：新版论文主线、P3计划、核心指标合同、历史缺口清单。它们是本任务首要依据，内部S1—S8来源沿用原材料。

本包未自行把HIAA/ALR/RIR更换为外部定义。P5-RX0/RX1、画像字段与试验规模是本次新增建议，明确为未来提案。

## S2：本轮只读核对的GitHub数据入口

仓库`Suuuu123su/Agent-SkillFlow`；读取时main为`06e78a602caf074c0e2593f9dd057c13ea4de7cc`。

`datasets/t17-v2/README.md`，blob `d8ed945acc1dc1ee2d558a036b765997e0377e50`：确认分卷、F/G与H复用边界以及纯离线report命令。

T17数字来自S1所附历史报告转录，不是本轮独立原始数据复算；本包不会把这些转录标为P3结果。

## S3：本轮只读核对的Evidence源码

`benchmarks/clawtrojan/README.md`，blob `867d3c119ff77d11bbb36cee02601dcc23915f8a`：确认v3冻结目录与历史原版目录、上游快照及限制。

`benchmarks/clawtrojan/frozen/src/evidence_v3/semantic_review.py`，blob `d1be0d7787e5ab2620fcc6225f022bf367025f84`：读取了路由提示、project_context、validate_route、ensure_effect_review及部分组件/请求构造。确认可见字段和当前意图到Content/Derived的映射；未证明本地最新运行所有代码与该快照一致。

这个入口未显示HIAA/ALR/RIR统计作为显式路由输入。此结论限该冻结入口，不扩大为“全项目从未使用结构证据/指标”。本轮没有实例化语义审查器或调用提供方。

## 本包做了什么、没做什么

已做：读用户指定文件、只读核对上述GitHub入口、生成任务文档/机器范围/模板、核对文件哈希与文档链接。

未做：P3事实级复算、完整当前仓库审计、运行实验/业务工具、修改Evidence算法、GitHub写入、新金标准或人工审阅。

`PACK_CHECKS.json`只证明任务包内部检查；不能当作项目P3验收。
