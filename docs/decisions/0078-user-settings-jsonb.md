# 0078 用户配置使用业务库 JSONB

- DATE: 2026-10-10
- TAGS: data, security, agent
- STATUS: 当前
- SUPERSEDES: —

## DECISION

少量、非敏感的用户偏好存业务 PostgreSQL 的 `user_settings`：每个用户最多一行，以 `user_id` 为主键，`config` 为带 `version` 的 JSONB。`agent_tools.always_allow` 按工具名保存布尔值；缺失即默认需要逐次审批。`timezone` 由已登录浏览器检测 IANA 时区并自动保存，Agent 创建任务时由业务服务读取；未保存则用实例默认时区，模型不参与选择。设置通过归属受控的业务 API 读写，修改单项时在数据库内原子更新对应 JSON 路径，保留同一用户的其他配置。已有 `user_tool_authorizations` 值迁入后删除旧表。新增配置项在 API 边界做类型与允许值校验。

LLM API Key、登录令牌及 AgentScope 凭据仍使用各自既定存储，不进入用户配置 JSON。AgentScope 通过现有内部认证接口读取当前用户设置，不直接访问业务表。

## REJECTED

- 每个用户一份对象存储配置文件：小配置的频繁读取与局部更新需要额外一致性和缓存机制。
- 每种配置项单独建表或按 `(user_id, tool_name)` 逐项保存偏好：当前少量设置不值得增加表与迁移负担。
- 为用户配置引入 Redis：单机、小并发下 PostgreSQL 主键读取足够，额外缓存会增加失效与运维复杂度。
- 将凭据混入通用 JSON 配置：破坏现有加密与归属边界。

## OUT OF SCOPE

通用设置界面、配置同步到客户端、跨实例缓存、配置历史版本。

## OPEN

无。
