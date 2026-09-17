# T18 独立构念附表

主机制表之后的受控接口/构念证据，绝不与T17 Live合并。308个保存核心已从原事实计算任务、风险与UEA；分别与原保存投影核对，共308×4项一致。22组四格按T18自己的冻结matrix和task risk selector绑定，metadata.harm_selector为空不被补成零。

|域|核心|保存Replay|UEA操作|TaskSuccess|SafeTaskSuccess|TP/FP/FN|来源F1|有符号CI|
|---|---|---|---|---|---|---|---|---|
|scripted|264|16|17|208/264|182/264|2352/0/0|1.0|16/16|
|fake_reference|44|5|4|32/44|26/44|343/0/0|1.0|5/5|

这些是构造样本，来源F1=1不能说明自然模型的追踪质量为1。Scripted 与 Fake/Reference 也不共用分母。按split/模式的完整分层见 `tables/T18_STRATA.csv`，四格及描述性差见 `tables/T18_HIAA_CELLS.csv`、`tables/T18_HIAA_CONTRASTS.csv`。每组局部四格只有冻结样本，不给自然总体区间。

本附表没有重新执行Scripted或Fake模型，也没有重新Replay。它不替代P4证据消融。
