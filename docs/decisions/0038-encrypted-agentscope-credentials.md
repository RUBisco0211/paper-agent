# 0038 AgentScope Credential 的 API Key 加密存储

- DATE: 2026-10-05
- TAGS: security, agent
- STATUS: 当前
- SUPERSEDES: —

## DECISION

继续使用 AgentScope Credential API、归属规则与模型引用；在 SQL 存储适配层加密 API Key，独立加密密钥只由 agent_service 持有。列表和更新响应不回传明文 Key；模型运行时按归属读取并解密。服务端限制凭据类型、模型目录与 Base URL，浏览器不能自由指定请求目标。

## REJECTED

- 直接沿用框架 SQL JSON 明文存储：数据库备份或只读泄露会暴露所有 Provider Key。
- 暂缓迁移：旧前端继续把 Key 放在浏览器本地存储，无法完成 R5 的跨会话凭据引用。
- 自建凭据表替代 AgentScope Credential：违反 0015 已定的框架模型配置路径。

## RATIONALE

AgentScope 2.0.6 的 `AsyncSQLAlchemyStorage.upsert_credential` 将 `SecretStr` 展开为 JSON 数据；需要在入库前加密，在模型装配时解密。

## OUT OF SCOPE

多密钥轮换、团队共享凭据、前端自由输入 Base URL。

## OPEN

已有浏览器本地 Key 的一次性迁移与清理方式随 R6 前端换基座确定。
