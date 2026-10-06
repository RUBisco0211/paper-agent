# 0027 检索能力在业务服务，toolkit 经 HTTP 调用

- DATE: 2026-10-05
- TAGS: agent, api
- STATUS: 当前
- SUPERSEDES: 0011 中「in-process toolkit 零 IPC」的论据（结论不变）

## DECISION

检索与文献能力由**业务服务**以 HTTP API 提供。agent_service 侧的 toolkit 函数内部经 HTTP 调用它，范围校验在业务服务端按 `session_id` 查 `session_binding` 后闭合。**agent_service 不直连业务库。**

## REJECTED

- toolkit 直连业务库做向量与全文检索：等于让 agent_service 依赖业务表结构，违反 0007 的边界约定。
- 业务侧包成 MCP server：多一层协议封装与一跳进程，且范围隔离要在 MCP 侧再实现一遍。
- 把检索实现复制进 agent_service：同一份 pgvector 逻辑两处维护，参数与索引必然漂移。

## RATIONALE

0011 定的是**形态**（toolkit 而非 MCP），本条定的是**调用路径**。文献服务与 agent 分进程后「零 IPC」不再成立，但 toolkit 仍比 MCP 少一层封装 —— 结论不变，只是理由要换。

## OUT OF SCOPE

以 MCP 对外暴露检索能力、把检索下沉到 agent 侧。

## OPEN

业务服务检索 API 的内部认证方式：mTLS、共享密钥，还是复用用户 JWT。
