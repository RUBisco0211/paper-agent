# 0008 业务服务签发 JWT，agent_service 覆盖 get_current_user_id

- DATE: 2026-10-05
- TAGS: security, api
- STATUS: 当前
- SUPERSEDES: —

## DECISION

注册、登录、Argon2id、JWT、refresh 轮换全部在业务服务（FastAPI）。agent_service 侧只需一行：`app.dependency_overrides[get_current_user_id] = 校验 JWT 并返回 users.id`。两侧共用同一套 `user_id`（业务库 `users.id`），会话归属不再冗余一层。验签用共享对称密钥。**只有一套认证逻辑、一个用户库。**

## REJECTED

- 前置 ASGI middleware 注入 `X-User-ID`：绕开官方入口，它升级改认证逻辑时易碎。
- 反向代理层做认证：拿不到业务 `user_id`，会话归属还得自己建一套。
- 两个服务各用一套用户表与认证：用户数据双写，一致性无从保证。
- 接第三方 IdP：多一个部署依赖，个人自用场景无收益。

## RATIONALE

框架默认实现就是读 `X-User-ID` header，注释原文写着 *Temporary header-based identity; will be replaced by JWT auth* —— 覆盖该依赖是官方留的扩展点，不是 hack。

## OUT OF SCOPE

第三方 IdP、SSO、多租户隔离（用户间隔离已由 `user_id` 保证）。

## OPEN

密钥分发方式（环境变量共享 vs JWKS）；refresh token 失效如何传播到 agent_service。
