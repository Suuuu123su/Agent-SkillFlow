# 离线复算

需要Python 3.11+标准库，无第三方依赖、Key、SDK、网络或业务执行器。解包到E盘新目录；所有新输出写在该目录的reproductions子目录。

```powershell
python -X utf8 -B .\code\reproduce_offline.py
```

默认64条覆盖所有核心机制的查询×13视图；逐条对照已归档预测。预测器进程不读取参照或旧预测，比较器仅在其落盘后对照。

如审查者明确要独立完整复算：

```powershell
python -X utf8 -B .\code\reproduce_offline.py --full
```

此命令从BASE_DOCUMENTS重新生成13许可视图，处理全部19,392固定查询，重建独立参照与分层长表。它是提供给审查者的入口；本轮未执行第二次完整扫掠。

最小包包括全部规范化许可事实、全部查询、裁剪的独立原事件/有限规则/来源oracle。原source文件不在此目录仍可复算。投影及裁剪输入使用自己的哈希；原始文件哈希/定位在SOURCE_MAP和QUERY_REGISTRY。

不运行task_pack/tools或其他旧launcher。code中的bootstrap/build_inputs等是入口生成审计源码，需原仓库，仅供审查；便携入口不调用它们。每个输出文件使用新目录，禁止把旧事实目录当输出目录。
