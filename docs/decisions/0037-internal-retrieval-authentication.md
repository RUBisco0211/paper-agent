# 0037 AgentScope 内部检索请求使用独立密钥

- DATE: 2026-10-05
- TAGS: security, api
- STATUS: 当前
- SUPERSEDES: —

## DECISION

agent_service 调业务服务的内部文献与检索 API 时，使用独立于用户 JWT 的服务间密钥认证，并传 `user_id` 与 `session_id`。业务服务验证密钥后，必须查询 `session_binding`，确认绑定属于该用户，再从绑定读取不可由工具参数扩大的范围。未绑定、归属不符或密钥无效均拒绝。

## REJECTED

- 透传用户 JWT：当前 `extra_agent_tools` 工厂只收到 `user_id`、`agent_id`、`session_id`，没有原始 Bearer token；补请求上下文会扩大框架耦合。
- mTLS：单机 Compose MVP 需额外维护证书配置与轮换。
- 只相信 AgentScope 传的用户 ID：业务服务无法鉴别调用方。

## RATIONALE

保持 AgentScope 不直连业务库，并让业务服务独立完成会话归属与范围授权。

## OUT OF SCOPE

将内部密钥暴露给浏览器、把内部 API 作为公开用户检索入口。

## OPEN

无。
