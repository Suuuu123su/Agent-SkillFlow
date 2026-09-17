# 离线复核

最小切片：解压审查ZIP到任意新目录，使用Python 3.10+执行 `python -B review_slice/recompute.py`。仅标准库，全部输入相对路径；输出 `review_slice/RECOMPUTED.json`。脚本主动拒绝网络、子进程和凭据文件读取。请不要执行task_pack或live中的实验启动器来复核离线指标。

完整历史分析入口为 `analysis/diagnose_m2.py`、`recover_mechanisms.py`、`independent_legacy.py`、`ci_raw_audit.py`；它们需要SOURCE_MANIFEST指向的原仓库事实，不属于最小切片独立性承诺。新Live事实投影为 `analysis/analyze_live.py`，不发请求。计算代码与模型执行代码分目录保存。

`legacy/METRICS_LONG.csv`保持旧P3字节与路径合同；其相对source_refs以同级原P3目录为根。新合并长表以analysis_layer区分版本。切片的独立核对器不调用生产指标函数；CLI传输/模型输出不在离线复核依赖中。

新参考引擎只实现本地动作级Grant匹配，scope文字是合成场景说明，不是生产完整Scope解析器。敏感network.send无结构Grant，因而相关UE分类不依赖任务ticket是否填写正确；业务成功另核。完整旧T17授权独立检查实现原Scope/Lifetime合同。
