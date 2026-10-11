# 0015 AgentScope Credential 与按用户派生的密钥

- DATE: 2026-10-05（2026-10-09 合并整理）
- TAGS: security, agent
- STATUS: 当前
- SUPERSEDES: 0004、0038、0039

## DECISION

LLM API Key 使用 AgentScope Credential API，服务端持有并跨会话按归属引用；会话模型配置仅持有 `credential_id` 与模型名。业务注册的 JSON Schema 限定凭据类型、模型目录与 Base URL 白名单，浏览器不能指定任意请求目标。列表与更新响应不回传明文 Key；Key 不进入日志、对象存储或任务队列。

AgentScope SQL 存储适配层在写入前加密 API Key，模型装配时按归属解密。agent_service 持有一个独立随机主密钥，以用户 ID 派生对称密钥，并将用户与凭据 ID 绑定进密文认证。主密钥不入数据库或浏览器；本地首次生成并持久保存，生产从受限密钥文件或环境配置读取。已有密文而主密钥丢失时明确失败，不自动重建。

## REJECTED

- 仅随请求提交 Key、不落库，或继续放浏览器存储：绕过 AgentScope 凭据引用和跨会话复用。
- 直接使用框架 SQL JSON 明文，或自建另一套凭据表：前者泄露风险高，后者重复管理能力。
- 自由输入 Base URL：会将请求目标交给前端。
- 所有用户直接共用同一数据密钥、逐用户另存随机密钥，或用非对称加密：分别缺少隔离、增加密钥库，或无法避免服务端解密。

## OUT OF SCOPE

主密钥轮换、外部 KMS、多实例共享密钥、团队共享凭据、按用量计费。

## OPEN

存量浏览器 Key 的迁移与清理若仍需支持，另行确定；主密钥须受限访问并备份。
