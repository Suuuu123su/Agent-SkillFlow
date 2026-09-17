# 两种不同的复现范围

本包是文稿审查包，不是单包可重跑全实验的镜像。没有重新内嵌P3/P4大包，也没有13组完整预测副本。

## 本轮三表与案例

在E盘新目录解包，使用Python 3.11+标准库：

```powershell
python -X utf8 -B .\code\render_tables.py
```

该入口只读取本包data/closeout_data.json和data/case_evidence_bindings.json，生成Markdown、UTF-8 CSV、LaTeX片段与六张案例卡；不导入预测器、不访问网络或调用模型。LaTeX仅交片段，需要使用方现有中文排版环境和longtable；本轮不编译PDF。论文段落与限制属于本轮整理文字。

如果要核对整理数据从何而来：SOURCE_MANIFEST逐项记录本地源路径/哈希，collect_saved_results.py说明本轮唯一一次已保存预测重聚合。该脚本需要原P4和P3R目录，且会拒绝覆盖已有closeout_data.json；不要为了补绿重新执行它。表内source_ref是相对仓库的原件定位，行号/JSON pointer属于原包。

## 原P4预测复算（仅供未来审查者）

取得DEPENDENCIES.json中的原P4 ZIP并核对准确SHA256后，依原包REPRODUCE.md使用其code/reproduce_offline.py。原P3/P3R机制来源另需列出的原P3R包。本轮没有改变这些路径，没有调用该预测器，也没有重跑64×13切片。

既有作者便携记录、作者ZIP记录与外部机械复核报告分别保留；它们都不是本轮新增832条验证，不能累计成新实验数量。本轮只做文档生成、保存结果加总、别名、链接与哈希检查。
