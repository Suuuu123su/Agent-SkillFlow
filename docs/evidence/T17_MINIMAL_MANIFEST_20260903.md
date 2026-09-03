# T17 最小离线证据清单（2026-09-03）

本清单仅对应新协议 `t17-minimal-technical-v1`、普通任务 evaluator `2.0.0`。
旧 T16/T17 Raw、失败 Attempt、历史 Summary 与指标未合并或改写。

## 新 Raw（仅本地）

所有路径相对于项目根。每域 23 core、12 Replay，1 semantic instance × 1 primary repeat，API=0。
Raw 根中的 `raw-manifest.json` 对每个文件登记 SHA-256、字节数和 JSONL 记录数；表中数量不含清单自身。

| 域 | 本地 Raw 根 | 已登记文件 | 字节 | JSONL 文件 / 记录 |
|---|---|---:|---:|---:|
| Scripted | `runs/t17-minimal-scripted-20260903-01/execution` | 1041 | 7836445 | 46 / 521 |
| Fake Reference | `runs/t17-minimal-fake-reference-20260903-01/execution` | 1041 | 7849707 | 46 / 521 |

| 对象 | SHA-256 |
|---|---|
| Scripted Raw manifest（文件字节） | `4dbd835c780a2a4cca5e88709d1be50cfb6e4570b56812678a2ecce23b7aa65c` |
| Fake Reference Raw manifest（文件字节） | `b5809b9594398e75b664d21953b60c4dcb16084cb7207b1339e40243ab984d94` |
| Scripted Phase Contract（canonical JSON） | `096f9ae0bf0a3aa7116bce57ff0f23108a79a4b05c27bfd68124320797c0ef1b` |
| Fake Reference Phase Contract（canonical JSON） | `55611bff4be9be4840930cc4ff7dee6cbf2539748a5eaf3ce5717578d0fa50a8` |

同名 Run ID 必须以 domain、Phase hash、Raw root 联合识别；不得跨域合并。Raw 清单包含存储、Blob、Trace、Graph、Run、Replay、普通任务证据、Phase 和执行状态。源代码或 Schema 字节漂移会阻断复算。

## 发布产物（不含 Raw 正文）

| 相对路径 | SHA-256（文件字节） |
|---|---|
| `experiments/t17/minimal-v1/preregistration.yaml` | `4ff745c38f26b8d3c4f5a2872429b48bd8fc0220269f28c34dca3d1955fb7318` |
| `experiments/t17/minimal-v1/matrix.yaml` | `ce32e2fa5eec11a6ec8a940f5a96368c54bed4758fba66e22f035520d5e9e8e0` |
| `docs/evidence/t17-minimal-scripted-metrics-20260903.json` | `9c396c56e0d81a6bd0c9ec2e0c317429d0f5a5b7022431c324b3af6a06269ead` |
| `docs/evidence/t17-minimal-scripted-metrics-20260903.csv` | `bcf5ab8aedcb8ca6df786861c6a15861a04c859dea3e47ce4347bc87f8dd38ff` |
| `docs/evidence/t17-minimal-fake-reference-metrics-20260903.json` | `7922159f45829d504a2fb25f5d7ad45c79500cca537de61ab776c0b83b55c5e9` |
| `docs/evidence/t17-minimal-fake-reference-metrics-20260903.csv` | `f1b6896395abc372ee0ec8c36e6f7d57a9a7194509acbafaee2b780d4b2d6eff` |

## 开发与失败记录

开发测试、red/green JUnit 和失败 Attempt 位于新的 `.tmp/t17-minimal-*` 目录，正式分母不包含它们。M1 的最终定向证据：

- `.tmp/t17-minimal-work-20260903-01/integration-final-01.xml`：24 passed；SHA-256 `41ec65240b9641004e6b2f6cfa49f58dee1951d91d002a5b6946b4c7b80d2faa`。
- `.tmp/t17-minimal-work-20260903-01/unit-edges-01.xml`：47 passed；SHA-256 `67c58cb5e14e67532864d84da80357c59af2beaa5e429517ad3834278a156710`。
- 首轮 Matrix 清单登记失败和后续断言失败均保留，详见 [M1 Summary](../summaries/T17M1_Summary.md)。不删除、覆盖或合并失败记录。

本清单不表示独立审查通过；审查者独立性仍为 `REVIEW_UNAVAILABLE`。完整技术验收以 M3 质量证据和最终 Summary 为准。
