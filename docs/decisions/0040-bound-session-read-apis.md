# 0040 会话绑定与引用提供用户读取接口

- DATE: 2026-10-06
- TAGS: api, security, frontend
- STATUS: 当前
- SUPERSEDES: —

## DECISION

业务服务提供按当前 JWT 用户过滤的会话绑定列表，以及按用户、会话和已登记 Citation ID 读取原文证据的接口。前端用 `session_id` 将绑定与 AgentScope 会话列表拼接，按全局和项目分组。引用卡片从已登记的检索工具结果取得 ID，点击后由业务服务再次校验归属；浏览器不能读取内部检索接口。Credential 的自定义 Base URL 由服务端配置选定，浏览器省略该字段。

## REJECTED

- 浏览器携带内部服务密钥读取引用：会泄露服务间凭据。
- 业务服务读取或 JOIN AgentScope 表来生成会话列表：破坏 0007 的数据边界。
- 接受未登记的模型输出 Citation ID 直接定位 PDF：绕过证据与归属检查。

## RATIONALE

AgentScope 管会话历史，业务库管项目范围和证据登记；各自按归属读取后在前端用 ID 拼接即可满足列表与原文核对。

## OUT OF SCOPE

跨库事务、会话范围变更、精确区域高亮。

## OPEN

无。
