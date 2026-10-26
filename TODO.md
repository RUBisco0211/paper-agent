# TODO — Agent 后端重构任务清单

> **工作态文件，不是规范。** 权威约束只有两个：`AGENTS.md`（常驻约定）和 `docs/DECISIONS.md`（决策）。
> 本文件只回答「现在做什么、做到哪、怎么算做完」，**不复述任何决策理由**，需要理由时按编号去 `docs/decisions/` 读那一条。
> 重构全部完成后删除本文件。

## 开工前必读（按顺序）

1. `AGENTS.md` —— 项目背景、硬约束、Never do
2. `docs/DECISIONS.md` —— 索引，重点看 0006–0016（架构）、0018–0034（业务与前端）
3. `docs/research/agentscope/agentscope-agent-service.md` —— agent_service 能力边界与源码锚点
4. `docs/research/agentscope/agentscope-web-ui.md` —— 前端基座与四个改造锚点

## 目标形态（一图）

```
浏览器 ──JWT──> 业务服务 FastAPI（论文库 / 项目 / 摄取 / 检索 / 认证）──> PostgreSQL 业务库
        └──JWT──> agent_service（会话 / 消息 / SSE / 中断 / 凭据）──> PostgreSQL as 库
                        ↑ extra_agent_tools 注入检索 toolkit ──HTTP──> 业务服务 /v1/search
摄取解析：独立 worker 进程，共享业务库当队列
```

## 里程碑

每个里程碑独立可验收。R6 的自动门禁与 DeepSeek 浏览器主路径已通过；R8 服务端并行负载已回测，用户已确认 R8 没有问题。

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

### R6 前端换基座（代码、自动门禁与 DeepSeek 浏览器主路径已完成）

- 以 web_ui 为底座：沿用布局、消息渲染、SSE 消费；改 `buildHeaders` 接 JWT、改会话列表按项目分组、注册自有 tool renderer 渲染引用卡片
- 迁移特有页面：论文库、项目、原文阅读器、引用
- **验收**：`pnpm run typecheck && pnpm run test && pnpm run build` 通过；能走完「上传 → 检索 → 提问 → 打开引用原文」
- **依据**：0014、0033、0032

**已实测**：浏览器注册 → 上传含正文的合成 PDF → worker 处理为可检索 → 项目范围提问 → 打开已登记引用片段 → 切换 DeepSeek 模型再问；另覆盖无证据、刷新历史、停止生成、删除带会话的项目与第二用户越权访问。
**已回测**：服务重启后，刷新历史可见“上次回答已中断”；流断开重连、项目侧栏刷新和检索故障与无证据区分有自动测试覆盖。
**用户确认**：R8 不再有待处理问题；此前列出的浏览器边界项未留存逐项回测记录。原内嵌 PDF 空白问题已改用 PDF.js 页面内渲染并通过自动测试。合成测试文献不代表实际论文质量验收。

### R7 后端瘦身与解析独立（代码与自动门禁已完成）

- 摘掉自研 sessions / agent 执行 / conversation 事件总线（先确认 R1–R4 已覆盖其行为）
- MinerU 解析拆为独立 worker 进程
- **验收**：`cd backend && uv run pytest -q` 全绿；解析任务由独立 worker 领取，API 进程不执行 MinerU；多页 PDF 与真实会话的服务端并行实测见 R8
- **依据**：0012、0016

### R8 端到端验收（DeepSeek 浏览器主路径已通过；用户确认无问题）

- 按 0031 的验收口径跑一遍完整用户旅程
- **验收**：`./start.sh` 起全套，浏览器走通「注册 → 上传 → 等解析 → 建项目 → 提问 → 点引用打开原文 → 切模型再问」
- **实测**：上述主路径已通过；引用弹窗加载了第 1 页的登记片段；服务重启后刷新可见中断提示。服务端接口回测中，授权 PDF 响应可解析，双次 SSE 连接和历史读取成功，混合检索返回证据；80 页合成 PDF 的 worker 处理期间，真实会话完成且历史接口持续响应，入库最终成功。
- **用户确认**：R8 无待处理问题；浏览器不刷新时的生成中断恢复、检索故障提示、PDF.js 内嵌画面与解析期间的会话交互未留存逐项回测记录。80 页合成 PDF 回测只验证并行流程，不代表真实大文件的资源压力。

### R9 并发入库与解析产物（自动门禁与真实服务回测已通过）

- 单 worker 有界并发处理不同论文；相同 PDF 并发入库只生成一篇论文与一个活跃 job
- MinerU 产物按 job 版本写入对象存储，完整清单发布后才切块；失败写入清理半成品
- Chunk 保存来源字符范围与可用坐标，已登记引用保留产物版本和来源位置
- **验收**：真实 PostgreSQL 并发/故障/重试测试通过；生产环境必须连通 S3 兼容对象存储
- **已回测**：本地 RustFS（真实 S3 兼容服务）上的对象存储测试与完整后端测试通过：191 passed、1 skipped，覆盖写入、读取、清理及相关 API 路径。
- **已回测**：两篇公开论文（15、16 页）同时调用真实 MinerU；两个正文解析阶段重叠且均成功，产物清单分别包含 17、19 个文件。隔离 RustFS 停机时返回稳定 503，重启后旧对象可读且可继续写入；摄取中注入写入中断后半成品清理、重试成功。
- **用户决定不再回测**：接近上传上限的大 PDF 资源压力及生产级 S3 部署；现有实测仅覆盖较小样本和本地 RustFS。生产部署仍须使用可用的 S3 兼容对象存储。
- **依据**：0056

## R10 入库记录模型重做（进行中，依据 0093、0094）

### 数据层

- [x] 迁移：删 `paper_imports`、`import_stages`
- [x] 迁移：建 `downloads`（user_id / identifier_type / identifier / status / paper_id / run_id / source_url / error_message / 时间戳）
- [x] 迁移：建 `runs`（paper_id / status / current_stage / stage_timings JSONB / error_message / leased_until / started_at / finished_at）
- [x] 迁移：建部分唯一索引 `(paper_id) WHERE status IN ('pending','running')`
- [x] 迁移：建 `user_runs`（user_id / run_id / paper_id）
- [x] 迁移：`user_papers` 删 `ready`、删 `source`
- [ ] 迁移：`chunk_metadata` 去 `artifact_manifest_key` 副本
- [x] 迁移：`papers` 保留 byte_size / page_count / mineru_version / metadata_sources / updated_at
- [x] ORM 与仓储：`downloads` 仓储、`runs` 仓储（含租约领取与过期回收）、`user_runs` 仓储
- [x] 删除 `PaperSource` 枚举、`MetadataStatus` 枚举、`ProviderMetadata.metadata_status()`

### 流程层

- [x] 上传入口：算 hash → papers 建/复用 → 按 paper_id 挂进行中 run（含 pending）或新建 run + user_runs
- [x] 导入入口：只建 downloads 行并返回，不下载
- [x] download worker：下载 → hash → papers 建/复用（补 doi/arxiv_id）→ 挂 run → 回填 paper_id / run_id
- [x] run worker：parse → chunk → embed，推进 current_stage 与 stage_timings
- [x] parse 阶段入口校验产物 sha256，不符则重新解析（不报错）
- [x] run 成功：按 paper_id 查 user_runs，逐个写入 user_papers
- [x] 租约续期与过期回收
- [x] 产物路径扁平化：删 `runs/{job_id}/`，删 `mineru_job_artifact_key` 与 `mineru_artifact_prefix`

### 接口与前端

- [x] 队列接口改为以 downloads 为行，串出关联 run
- [x] 删前端 `ERROR_TEXT` 映射，直接显示后端 `error_message`
- [x] 删除文献库对 `user_papers.ready` 的过滤

### 测试

- [x] 并发：两人同时导入同一 DOI 只产生一条 run
- [x] 并发：上传与下载得到同一 hash 时合并为同一篇论文
- [x] 失败：下载失败不建论文、不建 run，downloads 行保留
- [x] 失败：run 失败时所有挂靠用户可见同一结果
- [x] 崩溃：租约过期的 run 被判失败，续租的正常存活
- [x] 自愈：产物被截断后重试，parse 重新执行并成功

### R11 队列并入请求记录与项目归属（依据 0095）

- [x] 迁移：`user_runs` 加 `project_id`（可空，外键 projects）
- [x] `RunService.request` 接受 `project_id`，校验项目属于当前用户
- [x] 已完成论文的请求不写 `user_runs`，直接建 `user_papers` 与 `project_papers`
- [x] run 成功时：按 `paper_id` 反查 `user_runs`，先建 `user_papers` 再建 `project_papers`
- [x] 队列接口改为 `downloads` ∪ `user_runs`，按 `run_id` 去重
- [x] 上传接口把 `project_id` 传下去
- [x] 前端：列表只显示状态；详情按动作列步骤（导入含「获取原文」，上传含「文件上传」）
- [x] 测试：上传已在库的论文只建关系、不进队列
- [x] 测试：导入到指定项目后该条目出现在项目里
- [x] 测试：别人的项目 ID 被拒绝
- [x] 测试：队列里同一 run 只出现一次

### 待办（用户明确不急）

- [ ] 租约超时时长与失效判定的调优

## 全局约束（不重复，只指路）

- 不做清单与后置清单：`AGENTS.md` 第 1 节
- 禁止事项：`AGENTS.md` 第 5 节
- 语言约定：代码注释 / 日志事件名 / 错误码英文，用户可见文案与文档中文
- 提交：conventional commits，每个接口或功能一次提交

## 收尾

- 重构过程中产生的新决策，按 `docs/decisions/NNNN-*.md` 落一条并补进 `docs/DECISIONS.md` 索引，不要写进本文件
- 全部里程碑完成后删除本文件
