# A 成本稳健性与新执行验证

本目录实现一次预算受限的A-only验证，模型/Judge/付费API调用0。结果为PROMISING_LIMITED，4 sanity+24正式=28/48次，0重试；不自动扩样、不继续B。

- `registration`：先冻结成本、网格、候选集、缺证manifest、统计门槛及新样本规则。
- `attribution`：完整旧配对归因与必要性对照。
- `costs` / `sweep`：从头购证、仅旧development选静态、轨迹先封存再连接真值。
- `audit` / `statistics` / `report`：逐条核账、种子平均和任务族等权、Gate A。
- `fresh_runner` / `fresh`：授权/提交正交的真实文件/SQLite程序执行，原预测器/合同/oracle保持冻结。
- `fresh_report`：预先冻结的新批统计及Gate B。
- `delivery` / `verify_delivery`：事后呈现与只读交付复核，不修改实验规则。

[中文结果](../../论文材料/A成本稳健性与新执行验证_20260919/a-cost-20260919-2045/FINAL_REPORT_CN.md) · [准确入口和命令](../../论文材料/A成本稳健性与新执行验证_20260919/a-cost-20260919-2045/REPRODUCE.md)。

旧语义族的新实例不是新机制；新TaskSuccess增益来自正确识别未完成，不代表提高真实完成率。完整负结果与不可行预算保留。
