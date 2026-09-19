# 来源资格与版本

合格真实环境1个：OpenClaw npm 2026.8.1，实际build commit `ea806575e6450e4d1efdfc72c19f04be982a1b9b`。它不是旧任务pin 452e734；发行包完整SHA清单、npm完整性与锁文件绑定另存ENVIRONMENT_BINDING。官方脚本provider来自旧固定提交，明确替代模型决策，未替代执行层。

旧reference继承mock；旧OpenClaw安全sink只返回Receipt，来源标签是注入值。AgentDyn现有banking对象为内存业务模拟，不能作为本轮第二真实效果环境。只接入了一个额外安装，第二环境BLOCKED_EXTERNAL。

第一次直接HTTP工具write返回404；第二次完整agent路径因官方provider缺少一个源码依赖返回408；补齐公开依赖后唯一重试成功，文件字节独立匹配。安装57.86秒，成功资格场景16.25秒，属实测耗时；API usage中的计数来自脚本协议，不代表模型调用或计费。

公共读取来源：OpenClaw GitHub固定源码、npm registry的2026.8.1包。真实工具动作只涉及E盘独占文件夹。网关曾尝试刷新公开model catalog并被其网络检查阻断，日志保留；没有调用模型或真实账户。

公开来源链接：[官方脚本provider固定源码](https://github.com/openclaw/openclaw/blob/452e734022214f5f00bdd44cae675cc467c3cd85/scripts/e2e/mock-openai-server.mjs)、[npm固定发行元数据](https://registry.npmjs.org/openclaw/2026.8.1)。这些来源用于确认脚本协议与发行身份；本轮效果结论来自实际本地原始记录。
