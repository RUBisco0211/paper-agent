# 0015 LLM API Key 改用框架的 Credential 系统

- DATE: 2026-10-05
- TAGS: security
- STATUS: 当前
- SUPERSEDES: 0004（API Key 只随请求进入执行器，不落库）

## DECISION

API Key 改用 agentscope 的 Credential 系统：Key 落服务端、跨会话复用，按业务侧注册的 JSON Schema 校验。Base URL 继续禁止自由输入 —— schema 由业务侧注册，只列白名单 endpoint。

## REJECTED

- 保留 0004「Key 只随请求提交、不落库」：与框架凭据体系并行，模型配置路径要自己打通，且跨会话无法复用。
- Key 落服务端但用自建加密表：放弃它内建的凭据管理能力与 `/model` 联动，白付一份维护成本。
- 开放 Base URL 自由输入：等于把请求目标交给前端。

## RATIONALE

框架的 `SessionConfig.chat_model_config` 本身就是 `{credential_id, model}` 的引用式结构 —— Key 必须先在服务端存在，会话才能引用它。继续走「请求内提交」等于绕过它的模型装配，是逆着框架用。

## OUT OF SCOPE

多凭据轮换、按用量计费、团队共享凭据。

## OPEN

credential 的静态加密方案与密钥保护；存量用户浏览器里的 Key 如何迁移；日志中 `credential_id` 与 Key 的隔离是否足够（0004 的「不进日志」约束在 Key 上仍然有效）。
