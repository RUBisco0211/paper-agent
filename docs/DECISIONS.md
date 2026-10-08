# DECISIONS.md — 决策索引

> 索引，不是决策本身。正文在 `docs/decisions/NNNN-*.md`。
> 默认只读本文件；需要某条细节时再单独读那一条。**禁止批量读取 `docs/decisions/`。**

## 索引

### 架构与 Agent 后端（0001–0017）

| # | 标签 | 决策了什么 | 状态 | 文件 |
|---|------|-----------|------|------|
| 0001 | ingest | 去掉 GROBID，元数据走轻量 PDF 识别 + 在线标识符补全 | 当前 | [0001-drop-grobid.md](decisions/0001-drop-grobid.md) |
| 0002 | agent | Agent 执行固定用 AgentScope 原生模型层，模型目录来自 Model Card | 已被 0006 取代 | [0002-agentscope-native-models.md](decisions/0002-agentscope-native-models.md) |
| 0003 | arch | 业务服务为模块化单体，业务包固定七文件分层（agent / 会话层已移交） | 部分有效 | [0003-modular-monolith-layering.md](decisions/0003-modular-monolith-layering.md) |
| 0004 | security | LLM API Key 只随请求进入执行器，不落库、不进日志、不进对象存储 | 已被 0015 取代 | [0004-llm-key-request-scoped.md](decisions/0004-llm-key-request-scoped.md) |
| 0005 | arch | 后台任务与实时事件留在 FastAPI 进程内 | 已被 0006、0012 取代 | [0005-process-local-scheduling.md](decisions/0005-process-local-scheduling.md) |
| 0006 | arch, agent | Agent 后端核心改用 agentscope agent_service；KB 自研，不启用框架 Knowledge Base | 当前 | [0006-adopt-agentscope-agent-service.md](decisions/0006-adopt-agentscope-agent-service.md) |
| 0007 | data | 一个 PostgreSQL 实例两个 database；跨边界不 JOIN，应用层拼 session_id | 当前 | [0007-two-databases-one-instance.md](decisions/0007-two-databases-one-instance.md) |
| 0008 | security | 业务服务签发 JWT，agent_service 覆盖 `get_current_user_id`；一套认证一个用户库 | 当前 | [0008-jwt-override-current-user-id.md](decisions/0008-jwt-override-current-user-id.md) |
| 0009 | data | 不建 Entry 表，历史用框架的 `messages`；citation 放 `Msg.metadata` | 当前 | [0009-no-entry-table.md](decisions/0009-no-entry-table.md) |
| 0010 | agent | 上下文压缩用框架内建 `ContextConfig`，不自己实现 | 当前 | [0010-builtin-context-compression.md](decisions/0010-builtin-context-compression.md) |
| 0011 | agent | 检索以 in-process toolkit 经 `extra_agent_tools` 注入，范围在服务端闭合 | 当前 | [0011-in-process-retrieval-toolkit.md](decisions/0011-in-process-retrieval-toolkit.md) |
| 0012 | ingest | 解析跑独立 worker 进程，DB 当队列与协调者 | 当前 | [0012-parser-worker-process.md](decisions/0012-parser-worker-process.md) |
| 0013 | api | 不做 Node BFF，前端直连业务服务与 agent_service 两个 origin | 当前 | [0013-no-node-bff.md](decisions/0013-no-node-bff.md) |
| 0014 | frontend | 前端基于 web_ui 改造，跟 radix-nova 方言，停掉 base 迁移 | 当前 | [0014-frontend-on-web-ui.md](decisions/0014-frontend-on-web-ui.md) |
| 0015 | security | API Key 改用框架 Credential 系统，Key 落服务端；Base URL 仍禁自由输入 | 当前 | [0015-credential-system-for-api-key.md](decisions/0015-credential-system-for-api-key.md) |
| 0016 | agent | 用 interrupt + inbox hint 取代 steering / follow-up 双 pending 队列 | 当前 | [0016-interrupt-instead-of-pending-queues.md](decisions/0016-interrupt-instead-of-pending-queues.md) |
| 0017 | product | Cron 定时检索文献是要做的方向，不在 MVP；不写进不做清单 | 当前 | [0017-cron-scheduled-retrieval-post-mvp.md](decisions/0017-cron-scheduled-retrieval-post-mvp.md) |

### 产品与数据模型（0018–0046）

| # | 标签 | 决策了什么 | 状态 | 文件 |
|---|------|-----------|------|------|
| 0018 | data | 业务数据模型：全局 Paper + User Paper 两层，SHA-256 全局去重 | 当前 | [0018-business-data-model.md](decisions/0018-business-data-model.md) |
| 0019 | ingest | 摄取四阶段 + 阶段级重试，能力与状态分离 | 当前 | [0019-ingestion-stages.md](decisions/0019-ingestion-stages.md) |
| 0020 | ingest | Chunk 保留页码与版面定位（自研 KB 的核心理由） | 当前 | [0020-chunk-page-locator.md](decisions/0020-chunk-page-locator.md) |
| 0021 | product | 文献条目可以没有 PDF；对外用稳定条目 ID | 当前 | [0021-paper-entry-without-pdf.md](decisions/0021-paper-entry-without-pdf.md) |
| 0022 | security | 账号与登录态：JWT 15 分钟 + Refresh 轮换 + family 撤销 | 当前 | [0022-account-and-auth-session.md](decisions/0022-account-and-auth-session.md) |
| 0023 | product | 上传与个人文献库：先返回条目，再后台处理；不提供移除入口 | 当前 | [0023-upload-and-library.md](decisions/0023-upload-and-library.md) |
| 0024 | ingest | 元数据链路：前 5 页布局 → 识别 → 标识符在线补全 | 当前 | [0024-metadata-pipeline.md](decisions/0024-metadata-pipeline.md) |
| 0025 | product | 会话范围只有全局与项目两种；文献列表不注入提示词 | 当前 | [0025-session-scope-two-kinds.md](decisions/0025-session-scope-two-kinds.md) |
| 0026 | agent | 三个只读文献工具与 RRF 检索行为 | 当前 | [0026-readonly-paper-tools.md](decisions/0026-readonly-paper-tools.md) |
| 0027 | api | 检索能力在业务服务，agent 侧 toolkit 经 HTTP 调用 | 当前 | [0027-retrieval-via-http-api.md](decisions/0027-retrieval-via-http-api.md) |
| 0028 | agent | 会话与流式：模型目录、思考强度、停止与重连展示 | 当前 | [0028-session-streaming-remainder.md](decisions/0028-session-streaming-remainder.md) |
| 0029 | product | 引用与原文核对：按会话校验，无页码不编造 | 当前 | [0029-citation-and-source-view.md](decisions/0029-citation-and-source-view.md) |
| 0030 | product | DOI / arXiv 标识符导入；无 PDF 保留待补全文 | 当前 | [0030-identifier-import.md](decisions/0030-identifier-import.md) |
| 0031 | product | 端到端验收必须浏览器真实联调，样机与 mock 不算 | 当前 | [0031-e2e-acceptance.md](decisions/0031-e2e-acceptance.md) |
| 0032 | frontend | 界面文案只说状态 / 动作 / 后果；用语表与禁用项 | 当前 | [0032-ui-copy-rules.md](decisions/0032-ui-copy-rules.md) |
| 0033 | frontend | 前端以 web_ui 样式为底座做扩展：上游已有的直接沿用，特有部分在其体系内叠加 | 当前 | [0033-frontend-extend-web-ui.md](decisions/0033-frontend-extend-web-ui.md) |
| 0034 | product | 领域术语与禁用同义词 | 当前 | [0034-domain-glossary.md](decisions/0034-domain-glossary.md) |
| 0035 | security, agent | AgentScope 只验 access token，登出后最长 15 分钟失效 | 当前 | [0035-agent-service-access-token-revocation.md](decisions/0035-agent-service-access-token-revocation.md) |
| 0036 | arch, agent | 检索注入与会话范围合并为一个验收里程碑 | 当前 | [0036-merge-retrieval-and-session-scope.md](decisions/0036-merge-retrieval-and-session-scope.md) |
| 0037 | security, api | AgentScope 内部检索请求用独立密钥认证，再查会话绑定授权 | 当前 | [0037-internal-retrieval-authentication.md](decisions/0037-internal-retrieval-authentication.md) |
| 0038 | security, agent | Credential API Key 在 AgentScope SQL 存储适配层加密且响应脱敏 | 当前 | [0038-encrypted-agentscope-credentials.md](decisions/0038-encrypted-agentscope-credentials.md) |
| 0039 | security, agent | 单个服务端主密钥按用户派生对称密钥，主密钥独立持久保存 | 当前 | [0039-per-user-derived-credential-keys.md](decisions/0039-per-user-derived-credential-keys.md) |
| 0040 | api, security, frontend | 用户读取会话绑定与已登记引用，前端按 session_id 拼接 | 当前 | [0040-bound-session-read-apis.md](decisions/0040-bound-session-read-apis.md) |
| 0041 | agent, security | Agent 运行时只开放三个文献只读工具，现有 search_papers 承担 RAG 检索 | 当前 | [0041-agent-tool-allowlist.md](decisions/0041-agent-tool-allowlist.md) |
| 0042 | agent, product, ingest | 入读流程完成后增加基于 MinerU Markdown 的有界原文读取工具 | 当前 | [0042-bounded-paper-original-read.md](decisions/0042-bounded-paper-original-read.md) |
| 0043 | api, security, frontend | 删除会话先删 AgentScope，再删业务绑定与引用，并允许重试 | 当前 | [0043-bound-session-deletion.md](decisions/0043-bound-session-deletion.md) |
| 0044 | ingest, product, agent | 独立 worker 启动恢复中断任务；删除项目前清理 AgentScope 会话与绑定 | worker 部分已被 0056 取代 | [0044-r7-worker-and-project-lifecycle.md](decisions/0044-r7-worker-and-project-lifecycle.md) |
| 0045 | frontend, product | 对话页采用 web_ui 双层导航、项目文献侧栏和日历容器 | 当前 | [0045-conversation-layout-on-web-ui.md](decisions/0045-conversation-layout-on-web-ui.md) |
| 0046 | product, frontend, data | 定时任务必须归属项目；日历按项目显示任务 | 已被 0049 取代 | [0046-schedules-belong-to-projects.md](decisions/0046-schedules-belong-to-projects.md) |
| 0047 | product, agent, data, frontend | 项目自定义 prompt 用 AgentScope 定时触发；每次独立运行，任务页聚合结果 | 已被 0049 取代 | [0047-project-scheduled-agent-runs.md](decisions/0047-project-scheduled-agent-runs.md) |
| 0048 | frontend, product | 定时任务统一使用时钟入口与 `/scheduled`，默认月视图 | 当前 | [0048-scheduled-task-navigation.md](decisions/0048-scheduled-task-navigation.md) |
| 0049 | product, agent, data, frontend | 定时任务可选全局或项目范围；频率按星期选日 | 当前 | [0049-global-schedules-and-weekday-frequency.md](decisions/0049-global-schedules-and-weekday-frequency.md) |
| 0050 | product, frontend, agent | 定时运行可在任务页打开完整会话并继续对话 | 已被 0051 取代 | [0050-scheduled-run-conversations.md](decisions/0050-scheduled-run-conversations.md) |
| 0051 | product, frontend | 点击运行记录直接打开会话；时间按任务时区显示 | 当前 | [0051-scheduled-run-record-navigation.md](decisions/0051-scheduled-run-record-navigation.md) |
| 0052 | frontend, product | 定时任务侧栏沿用对话页的分组与条目样式 | 当前 | [0052-scheduled-sidebar-chat-style.md](decisions/0052-scheduled-sidebar-chat-style.md) |
| 0053 | frontend, product | 授权 PDF 用 PDF.js 在页面内渲染并支持引用页定位、翻页与缩放 | 当前 | [0053-embedded-pdf-rendering.md](decisions/0053-embedded-pdf-rendering.md) |
| 0054 | frontend, product | 删除定时任务等不可撤销操作统一使用站内确认弹窗 | 已被 0055 取代 | [0054-destructive-confirmation-dialogs.md](decisions/0054-destructive-confirmation-dialogs.md) |
| 0055 | frontend, product | 所有业务弹窗直接沿用 web_ui Dialog 与 Button 的样式 | 当前 | [0055-web-ui-dialog-standard.md](decisions/0055-web-ui-dialog-standard.md) |
| 0056 | ingest, storage, citation | 单 worker 有界并发；生产 S3 兼容存储；MinerU 版本清单与引用来源范围 | 当前 | [0056-concurrent-ingestion-artifacts.md](decisions/0056-concurrent-ingestion-artifacts.md) |
| 0057 | frontend, library, ingest | 文献在主区域阅读，右侧按 MinerU 原始 block type 导航与定位 | 当前 | [0057-paper-reading-mineru-blocks.md](decisions/0057-paper-reading-mineru-blocks.md) |
| 0058 | frontend, product | 文献处理进度按阶段顺序显示为步骤视图 | 当前 | [0058-ingestion-progress-stepper.md](decisions/0058-ingestion-progress-stepper.md) |
| 0059 | frontend, library, product | 文献块显示图片与公式预览，PDF 连续滚动并按可见页绘制 | 当前 | [0059-paper-block-previews-continuous-pdf.md](decisions/0059-paper-block-previews-continuous-pdf.md) |
| 0060 | frontend, library, product | PDF 叠加可选文本层并提供复制菜单；旧 MinerU 图片路径回退，公式优先渲染源码 | 当前 | [0060-paper-text-selection-and-legacy-previews.md](decisions/0060-paper-text-selection-and-legacy-previews.md) |
| 0061 | frontend, library | 文献阅读双栏统一工具栏高度，分块侧栏可拖拽，PDF 支持滚轮及键盘快捷操作 | 当前 | [0061-paper-reading-controls.md](decisions/0061-paper-reading-controls.md) |
| 0062 | frontend, library | 文献信息抽屉不再重复渲染 PDF；阅读页并行加载，图片和图表共用大图查看器 | 当前 | [0062-paper-preview-and-loading.md](decisions/0062-paper-preview-and-loading.md) |
| 0063 | api, library, cache | 授权 PDF 与不可变解析产物采用私有 HTTP 条件缓存，替换或重解析时换版 | 当前 | [0063-private-paper-http-cache.md](decisions/0063-private-paper-http-cache.md) |
| 0064 | frontend, chat | 项目文献入口放在项目行操作区，会话顶栏控制可调宽度的文献侧栏 | 当前 | [0064-chat-project-paper-sidebar.md](decisions/0064-chat-project-paper-sidebar.md) |
| 0065 | frontend, library, cache | 阅读页短时复用已授权 PDF 字节，替换文件后失效，并减少视口外预绘制 | 当前 | [0065-paper-reader-warm-cache.md](decisions/0065-paper-reader-warm-cache.md) |

状态取值：`当前` / `已被 NNNN 取代` / `已废弃`
标签：`ingest` / `agent` / `arch` / `security` / `api` / `data` / `product` / `frontend`

按触发场景找：

| 触发场景 | 读哪一组 |
|---|---|
| 改动 Agent 后端、会话、检索或凭据接入 | 0006–0017、0035–0039 |
| 改动产品功能范围、文献 / 摄取 / 引用行为 | 0018–0034 |
| 改前端文案或界面 | 0014、0032、0033 |
| 涉及领域术语与命名 | 0034 |

`docs/` 下只有 `DECISIONS.md`、`decisions/`、`research/` 三处；不符合这三处的文档已全部收敛或删除。

## 新增一条决策

1. 新建 `docs/decisions/NNNN-<短横线标题>.md`
2. 在本文件索引表补一行
3. **两步都做完才算完成** —— 只建文件不更新索引，等于这条决策不存在

正文模板：

```
# NNNN 标题

- DATE:
- TAGS:
- STATUS: 当前
- SUPERSEDES: —

## DECISION
## REJECTED
## RATIONALE
## OUT OF SCOPE
## OPEN
```

规则：

- **REJECTED 不能空** —— 它防止你下次绕回被否决的方案。可以没有 RATIONALE，不能没有 REJECTED。
- 决策写下后不再修改。要推翻就**新建一个文件**，原文件 STATUS 改为 `已被 NNNN 取代`。
- 单文件 ≤30 行。
- 只有影响后续取舍的才值得记。改个变量名不用记。
- 2026-09 之前的历史决策原文已删除，结论保留在 `0001` 及 0018–0034；推翻它们时新建条目并标注 SUPERSEDES。
