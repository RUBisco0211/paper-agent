# 0035 AgentScope 只按 JWT 有效期接受 access token

- DATE: 2026-10-05
- TAGS: security, agent
- STATUS: 当前
- SUPERSEDES: —

## DECISION

agent_service 只验证业务服务签发的 access token 的签名、发行者、类型和有效期，并以 `sub` 作为用户 ID。登出或 refresh token family 撤销后，已签发的 access token 在 agent_service 侧最多继续有效 15 分钟；业务服务仍按自身登录态规则即时拒绝请求。

## REJECTED

- 每次请求回查业务服务的登录态：让 agent_service 的所有 API 与 SSE 建连依赖业务服务可用性和额外请求。
- 两服务共享撤销表或缓存：引入第二套跨服务状态契约，与当前单机 MVP 的 15 分钟 token 生命周期不相称。

## RATIONALE

沿用 0008 的验签边界，保持 agent_service 不访问业务用户库；15 分钟是 0022 已确定的 access token 上限。

## OUT OF SCOPE

已建立 SSE 连接的即时断开、access token 黑名单、业务服务登出后的跨服务推送。

## OPEN

无。
