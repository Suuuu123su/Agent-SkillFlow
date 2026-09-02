# T17-A 总结：指标与既有证据冻结

- 状态：PASSED
- API 调用：0
- 基线 revision：c1d91cc89695485f428b20c34fde20c0a21f398a
- canonical 文件：53
- artifact set SHA-256：f663b1bf154b912fbbd84eab093abeadfd5f67ed7624d2b03092886d21397949

T17-A 新增了四态测量合同 measured、not_applicable、not_available、incomplete，
并将 Scripted、Fake Provider、Direct Prompt、Reference Harness 与合同 Schema 分域。
跨 Evidence Domain 的 micro 聚合由类型化守卫拒绝。

指标公式、统计单位、分母、Hook 要求和缺失规则已冻结在
docs/metrics/metric-registry.md。旧 T16 Schema 重新生成后没有字节差异；T16 Raw、
Matrix、合同与报告均未修改。

结构化证据：docs/evidence/t17-baseline-audit.json。

