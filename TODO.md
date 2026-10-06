# TODO — Agent 后端重构任务清单

> **工作态文件，不是规范。** 权威约束只有两个：`AGENTS.md`（常驻约定）和 `docs/DECISIONS.md`（决策）。
> 本文件只回答「现在做什么、做到哪、怎么算做完」，**不复述任何决策理由**，需要理由时按编号去 `docs/decisions/` 读那一条。
> 重构全部完成后删除本文件。

## 开工前必读（按顺序）

1. `AGENTS.md` —— 项目背景、硬约束、Never do
2. `docs/DECISIONS.md` —— 索引，重点看 0006–0016（架构）、0018–0034（业务与前端）
3. `docs/research/agentscope-agent-service.md` —— agent_service 能力边界与源码锚点
4. `docs/research/agentscope-web-ui.md` —— 前端基座与四个改造锚点

## 目标形态（一图）

```
浏览器 ──JWT──> 业务服务 FastAPI（论文库 / 项目 / 摄取 / 检索 / 认证）──> PostgreSQL 业务库
        └──JWT──> agent_service（会话 / 消息 / SSE / 中断 / 凭据）──> PostgreSQL as 库
                        ↑ extra_agent_tools 注入检索 toolkit ──HTTP──> 业务服务 /v1/search
摄取解析：独立 worker 进程，共享业务库当队列
```

## 里程碑

每个里程碑独立可验收。R6 的自动门禁已通过；真实 Provider 浏览器联调按本次约定延至 R8，不能据此宣称端到端验收完成。

### R1 起最小 agent_service（已用本地假 Provider 验证）

- 固定 agentscope 版本，按 `examples/agent_service` 起一个最小服务：独立 database + `AsyncSQLAlchemyStorage` + `InMemoryMessageBus`
- 一个最小 agent，跑通 `POST /chat/` → `GET /sessions/{sid}/stream` → `POST /sessions/{sid}/interrupt`
- **验收**：curl 触发一次会话，能看到流式文本、能中断、刷新后历史仍在
- **依据**：0006、0007
- **不做**：接业务、接认证、接检索

### R2 认证接入（已通过双服务 JWT 与 CORS 验证）

- 业务服务继续签发 JWT；agent_service 侧 `dependency_overrides[get_current_user_id]` 验签
- 前端两个 origin 都带同一个 JWT，CORS 配两处
- **验收**：无 token 与过期 token 访问 agent_service 被拒；用业务库 `users.id` 建的会话归属正确
- **依据**：0008、0022、0035

### R3–R4 检索注入与会话范围（已通过真实数据库与本地假 Provider 联调）

- 先在业务侧建 `session_binding`（`session_id` / `user_id` / `project_id`），支持项目与全局两种范围
- 业务侧 `/v1/search` 保持可用；agent 侧把三个只读工具改成 `extra_agent_tools` 工厂注入，内部 HTTP 调业务检索 API
- 范围在服务端闭合，工具不接受「范围」参数
- **验收**：项目内会话只命中该项目文献、全局会话命中全部；会话提问能触发检索并返回 `citation_id`；伪造范围调用被拒
- **依据**：0011、0025、0026、0027、0036、0037

### R5 凭据迁移（AgentScope 后端已验证；浏览器接入随 R6）

- LLM API Key 迁到 Credential 系统，Base URL 仍由服务端注册、不允许前端自由输入
- **验收**：配置一次 Key，新会话可用；Key 不出现在前端日志与业务库
- **依据**：0015、0038、0039（推翻 0004）

### R6 前端换基座（代码与自动门禁已完成；真实 Provider 浏览器联调待办）

- 以 web_ui 为底座：沿用布局、消息渲染、SSE 消费；改 `buildHeaders` 接 JWT、改会话列表按项目分组、注册自有 tool renderer 渲染引用卡片
- 迁移特有页面：论文库、项目、原文阅读器、引用
- **验收**：`pnpm run typecheck && pnpm run test && pnpm run build` 通过；能走完「上传 → 检索 → 提问 → 打开引用原文」
- **依据**：0014、0033、0032

**待回测**：配置有效 Provider 凭据，在浏览器完成「上传 → 检索 → 提问 → 打开引用原文」；覆盖无证据与检索故障、刷新与断线恢复、停止与删除、多用户隔离。此项与 R8 一起验收，不以测试凭据或接口测试代替。

### R7 后端瘦身与解析独立（代码与自动门禁已完成）

- 摘掉自研 sessions / agent 执行 / conversation 事件总线（先确认 R1–R4 已覆盖其行为）
- MinerU 解析拆为独立 worker 进程
- **验收**：`cd backend && uv run pytest -q` 全绿；解析任务由独立 worker 领取，API 进程不执行 MinerU；大 PDF 与真实会话并行的实测留到 R8
- **依据**：0012、0016

### R8 端到端验收（待办，含 R6 延后的真实 Provider 联调）

- 按 0031 的验收口径跑一遍完整用户旅程
- **验收**：`./start.sh` 起全套，浏览器走通「注册 → 上传 → 等解析 → 建项目 → 提问 → 点引用打开原文 → 切模型再问」

## 全局约束（不重复，只指路）

- 不做清单与后置清单：`AGENTS.md` 第 1 节
- 禁止事项：`AGENTS.md` 第 5 节
- 语言约定：代码注释 / 日志事件名 / 错误码英文，用户可见文案与文档中文
- 提交：conventional commits，每个接口或功能一次提交

## 收尾

- 重构过程中产生的新决策，按 `docs/decisions/NNNN-*.md` 落一条并补进 `docs/DECISIONS.md` 索引，不要写进本文件
- 全部里程碑完成后删除本文件
