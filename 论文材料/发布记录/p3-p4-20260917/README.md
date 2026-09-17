# P3/P3R/P4 发布说明

本次基于远端06e78a6发布已完成的P3、P3R、P4与P4结项；不包含本地较早的T19-R修改，不重跑模型或指标，不恢复暂停任务。

四份完整审查ZIP按原字节发布，来源映射见PUBLICATION_MAP.json。该映射记录99fc346时的历史树；后续52个展开任务包文件已改为archive-only，当前定位及还原方法见[迁移说明](../../../docs/releases/repo-restructure-20260917.md)和[机器映射](../../../docs/releases/repo-restructure-20260917.json)。单成员大于10 MiB的长表或事实中间表只存于其原ZIP，小文件另展开方便浏览。工作目录里的重复解包、验证副本和各视图缓存不重复入库。原合同、未知、缺口、分母及归档哈希不变。

## 完整审查包

- [P3_REVIEW_p3-20260916-232018.zip](../../P3_机制测量/p3-20260916-232018/P3_REVIEW_p3-20260916-232018.zip)：SHA256 `790950036f6893eab47588a8a30e9976c51b27aa0fabeaffe2c53fed87c9b67f`。
- [p3r-completion-review.zip](../../P3_机制测量/p3r-20260917-103400/p3r-completion-review.zip)：SHA256 `3390b1e8dba914cc42088661b5378d139ddce177c551f4e0d70a3d74e47ee304`。
- [p4-closeout-review.zip](../../P4_测量证据消融/closeout-20260917-141455/p4-closeout-review.zip)：SHA256 `82bf039de2c7b54a5951763021b4497e4356de98f590468094c2b9289d20dee3`。
- [p4-evidence-ablation-review.zip](../../P4_测量证据消融/p4-20260917-123623/p4-evidence-ablation-review.zip)：SHA256 `dcda387b143a72eb56dd53a1a03fe5aa934462eccf974181025b868bd8c1265d`。

## 读取与复现

直接审阅展开的论文三表、六案例及章节草稿。需要完整长表或运行已有离线复算入口时，将对应原ZIP解包至独立E盘目录，按包内REPRODUCE说明处理；不要运行归档中的Live启动器。P4收尾ZIP只支持文稿重建，原实验依赖仍见DEPENDENCIES.json；本次同时提供原P4/P3R审查包，并不补齐所有未公开历史来源。

归档中的“未提交/推送”是冻结生成时的历史状态，保持原字节。当前发布在本记录及Git提交中说明，不回写旧状态或重打包。P4管理状态CLOSED_WITH_DOCUMENTED_GAPS，人审0，框架唯一必要性未证明；F/H ToolReturn valid_only的P3R每格13与P4每格15差异仍保留。后续P1延期、P5/P6未启动。

本次只检查发布路径、归档字节、成员映射和入口链接；不新增实验验证。提交使用[skip ci]，不触发全量远端CI。
