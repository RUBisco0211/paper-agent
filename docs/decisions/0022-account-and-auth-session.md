# 0022 账号与登录态：JWT + Refresh 轮换 + family 撤销

- DATE: 2026-10-05
- TAGS: security, product
- STATUS: 当前
- SUPERSEDES: `docs/overview/minimal-mvp.md` F01（已删除）

## DECISION

注册 / 登录 / 刷新 / 登出，不做邮箱验证、找回密码、管理员。密码用 Argon2id。Access token 是有效期 15 分钟的 JWT，浏览器只存运行时内存；Refresh token 是 7 天高熵随机值，`HttpOnly + Secure` Cookie，库里只存哈希。每次使用都在事务内轮换，并发只能有一次成功；已轮换 token 再次出现则撤销整个 token family；登出撤销当前 family。签发在业务服务，agent_service 只验签（0008）。

## REJECTED

- 单 token 长有效期：泄漏窗口大且无法踢下线。
- 服务端会话存 Redis / DB：与「无 Redis」冲突，且多一处有状态依赖。
- 把 refresh 轮换放进 agent_service：它不该持有用户库（0008）。
- 邮箱验证、找回密码、管理员后台：MVP 不做。

## RATIONALE

轮换 + family 撤销是「能踢下线、能检测 token 复用」的低成本实现，代价只有一个事务内轮换的约束。

## OUT OF SCOPE

邮箱验证、找回密码、管理员、多设备管理界面、WebAuthn。

## OPEN

并发请求同时触发刷新时，前端如何避免重复轮换。
