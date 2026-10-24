# 0090 — Embedding 安全错误与请求级超时

- DATE: 2026-10-24
- TAGS: security, retrieval, ingest
- STATUS: 当前
- SUPERSEDES: 0087 中记录任意失败 details 的片段

## DECISION

- Embedding 错误只使用稳定的本地文案和结构化诊断，不复制上游错误正文到 AppError.message/details。上游可能回显 Key 或文献原文；这类信息不得进入响应、阶段错误记录或日志。
- 流水线日志只接收允许的整数诊断字段（HTTP 状态、数量、维度），不记录任意 details 字典。正常入库状态和用户重试方式不变。
- 上游结构错误与非数值/非有限向量在适配器边界转为安全错误，不能让原始值进入数据库转换异常。传输异常不透传原始异常文本。
- 响应 index 必须是非布尔整数，唯一且完整覆盖每批输入的 0..N-1，校验后排序；向量数值转换为 float32 后必须仍有限。只验证可存储性，不额外量化；正常舍入与下溢允许通过，并以真实 PostgreSQL pgvector 验证边界。
- `EMBEDDING_TIMEOUT_SECONDS` 只在请求上覆盖 read；factory 客户端的 connect/write/pool 超时保持不变，也不修改客户端对象。
- 重试预算为 N 次重试、最多 N+1 次请求，最终成功或耗尽后不得额外 sleep；离线测试覆盖零重试、最后一次成功、429、5xx 和 ReadTimeout。
- 设置页明确需要 SiliconFlow API Key，并提供获取入口，只说明检索消耗、入库费用及无 Key 时仅关键词检索，不解释内部存储和向量处理机制。

## REJECTED

- 原样展示或持久化上游错误：第三方响应不可信，可能回显凭据或原文。
- 记录任意 details 再依赖人工脱敏：新增字段会绕过日志安全边界。
- 改写整个客户端 timeout：会破坏调用方设置的连接、写入和池等待预算。

## OUT OF SCOPE

清理已有日志和业务错误记录、轮换密钥、改变重试策略或检索降级契约。
