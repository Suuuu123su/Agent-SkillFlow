# P2 Luna All：运行与分析结束

本Luna修订替代GLM默认方案。39/39选定阶段有有效原生判分；63次正式物理尝试含39首轮、16第一恢复、8第二恢复，全部旧记录保留。TECH四槽位：三项通过，一项外发前失败。

攻击C/P/S=17/5/4，正常=1/2/10。U真/假/未知=26/11/2；V=7/28/4；E_STS=24/11/4。辅助覆盖39/39，U/V均可判定34，人工复核0。历史39条均HISTORY_ONLY，不作受控排名。

累计1574次预算尝试，1573次外发尝试；21条历史响应未知未被改写，23条用量缺失。累计预算保护保持4096/单目标128/Actor20/辅助108/Judge47；实际Judge39。经用户授权截止延至20:00，实际18:56结束。

前74请求保留r1嵌套宿主工具声明遗漏；后1500请求为r2。后续传输/监控/账本修订单列，不能称全组统一上下文。

[最终报告](P2_FINAL_REPORT.md) · [全部选定结果](analysis/outputs/RESULTS39.csv) · [双向案例](analysis/outputs/CASEBOOK.md) · [审查包清单](P2_REVIEW_ZIP_MANIFEST.json)

本公开目录只含代码、脱敏协议和最终统计，不包含原始provider日志、认证、私有推理、运行中progress.json或完整审查轨迹。完整审查ZIP本地交付。代码中的机器路径已替换为占位符，原件/发布哈希见PUBLICATION_SOURCE_MAP；本目录不是可直接启动的新实验授权。

独立复算：`python analysis/verify_public_accounting.py review_materials/accounting/REQUEST_ACCOUNTING.jsonl` 与 `python analysis/verify_attempt_inventory.py .`。均只读保存数据。

P0保持结项，P1继续延期，不自动开始P1/P3/P4或其他模型。
