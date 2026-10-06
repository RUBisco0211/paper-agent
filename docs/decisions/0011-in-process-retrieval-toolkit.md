# 0011 检索以 in-process toolkit 注入，范围在服务端闭合

- DATE: 2026-10-05
- TAGS: agent, security
- STATUS: 当前
- SUPERSEDES: —

## DECISION

检索以普通工具函数形式，经 `extra_agent_tools` 异步工厂注入：签名 `(user_id, agent_id, session_id, workspace) -> list[Tool]`。会话范围（全库 / 项目 / 单篇）在服务端按 `session_id` 查 `session_binding` 后闭合，**模型无法通过工具参数越权**。混合检索（FTS + pgvector + RRF）与页码定位保持自研。

## REJECTED

- 包成 MCP server：每次调用多一跳序列化与网络开销，且范围隔离要在 MCP 侧另做一层（传参可被模型伪造）。
- 内部 toolkit + 对外再包一层 MCP：两处实现要保持一致，MVP 阶段属提前设计。
- 工具内部各自查范围：每个工具都要重复一遍归属校验，容易漏。
- 每个项目建一个真 Knowledge Base 只借 id：KB 自研后这层间接没有意义。

## RATIONALE

检索是一轮内可能多次调用的高频只读操作，延迟敏感；而范围隔离是关键安全属性，工厂签名天然在服务端闭合。KB 自研后 `knowledge_base_ids` 不可用，`extra_agent_tools` 是唯一官方注入点。

## OUT OF SCOPE

以 MCP 对外暴露检索能力、工具执行沙箱。**rerank 已从「明确不做」解禁为后置待评估项**，不再是否决项，但 MVP 仍以 FTS + pgvector + RRF 为基线。

## OPEN

工具返回结构如何携带可回查的 `citation_id`；一次返回多少 chunk 不撑爆上下文（与 0010 的 `tool_result_limit` 联动）；rerank 是否引入、以什么形态引入（重排服务 vs 本地模型）待评估。
