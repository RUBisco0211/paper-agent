# DECISIONS.md — 决策索引

> 索引，不是决策本身。正文在 `docs/decisions/NNNN-*.md`。
> 默认只读本文件；需要某条细节时再单独读那一条。**禁止批量读取 `docs/decisions/`。**

## 索引

### 架构与 Agent 后端（0001–0016）

| # | 标签 | 决策了什么 | 状态 | 文件 |
|---|------|-----------|------|------|
| 0001 | ingest | 去掉 GROBID，元数据走轻量 PDF 识别 + 在线标识符补全 | 当前 | [0001-drop-grobid.md](decisions/0001-drop-grobid.md) |
| 0003 | arch | 模块化单体七文件分层；文献归四个业务包，技术辅助能力集中在 literature_support | 当前 | [0003-modular-monolith-layering.md](decisions/0003-modular-monolith-layering.md) |
| 0006 | arch, agent | AgentScope 服务承载会话与模型；业务保留文献检索和证据；默认工具受限 | 当前 | [0006-adopt-agentscope-agent-service.md](decisions/0006-adopt-agentscope-agent-service.md) |
| 0007 | data | 一个 PostgreSQL 实例两个 database；跨边界不 JOIN，应用层拼 session_id | 当前 | [0007-two-databases-one-instance.md](decisions/0007-two-databases-one-instance.md) |
| 0008 | security | 业务服务签发 JWT，agent_service 覆盖 `get_current_user_id`；一套认证一个用户库 | 当前 | [0008-jwt-override-current-user-id.md](decisions/0008-jwt-override-current-user-id.md) |
| 0009 | data | 不建 Entry 表，历史用框架的 `messages`；citation 放 `Msg.metadata` | 当前 | [0009-no-entry-table.md](decisions/0009-no-entry-table.md) |
| 0010 | agent | 上下文压缩用框架内建 `ContextConfig`，不自己实现 | 当前 | [0010-builtin-context-compression.md](decisions/0010-builtin-context-compression.md) |
| 0011 | agent | 项目工具经 `extra_agent_tools` 注入 Toolkit 分组，范围在服务端闭合 | 当前 | [0011-in-process-retrieval-toolkit.md](decisions/0011-in-process-retrieval-toolkit.md) |
| 0013 | api | 不做 Node BFF，前端直连业务服务与 agent_service 两个 origin | 当前 | [0013-no-node-bff.md](decisions/0013-no-node-bff.md) |
| 0014 | frontend | 前端基于 web_ui 改造，跟 radix-nova 方言，停掉 base 迁移 | 当前 | [0014-frontend-on-web-ui.md](decisions/0014-frontend-on-web-ui.md) |
| 0015 | security, agent | AgentScope Credential 加密存储 API Key；服务端主密钥按用户派生对称密钥 | 当前 | [0015-credential-system-for-api-key.md](decisions/0015-credential-system-for-api-key.md) |
| 0016 | agent | 用 interrupt + inbox hint 取代 steering / follow-up 双 pending 队列 | 当前 | [0016-interrupt-instead-of-pending-queues.md](decisions/0016-interrupt-instead-of-pending-queues.md) |

### 产品、数据与界面（0018–0078）

| # | 标签 | 决策了什么 | 状态 | 文件 |
|---|------|-----------|------|------|
| 0018 | data | 业务数据模型：全局 Paper + User Paper 两层，SHA-256 全局去重 | 当前 | [0018-business-data-model.md](decisions/0018-business-data-model.md) |
| 0019 | ingest | 摄取四阶段 + 阶段级重试，能力与状态分离 | 部分失效（0091） | [0019-ingestion-stages.md](decisions/0019-ingestion-stages.md) |
| 0020 | ingest | Chunk 保留页码与版面定位（自研 KB 的核心理由） | 当前 | [0020-chunk-page-locator.md](decisions/0020-chunk-page-locator.md) |
| 0021 | product | 文献条目可以没有 PDF；对外用稳定条目 ID | 当前 | [0021-paper-entry-without-pdf.md](decisions/0021-paper-entry-without-pdf.md) |
| 0022 | security | 账号与登录态：JWT 15 分钟 + Refresh 轮换 + family 撤销；邮箱认证与 Redis 否决片段由 0081 取代 | 当前 | [0022-account-and-auth-session.md](decisions/0022-account-and-auth-session.md) |
| 0023 | product | 上传与个人文献库：先返回条目，再后台处理；不提供移除入口 | 当前 | [0023-upload-and-library.md](decisions/0023-upload-and-library.md) |
| 0024 | ingest | 元数据链路：前 5 页布局 → 识别 → 标识符在线补全 | 当前 | [0024-metadata-pipeline.md](decisions/0024-metadata-pipeline.md) |
| 0025 | product | 会话范围只有全局与项目两种；文献列表不注入提示词 | 当前 | [0025-session-scope-two-kinds.md](decisions/0025-session-scope-two-kinds.md) |
| 0026 | agent | 库内只读文献工具、RRF 检索与包含定时任务的运行时工具白名单 | 当前 | [0026-readonly-paper-tools.md](decisions/0026-readonly-paper-tools.md) |
| 0027 | api | 检索能力在业务服务，agent 侧 toolkit 经 HTTP 调用 | 当前 | [0027-retrieval-via-http-api.md](decisions/0027-retrieval-via-http-api.md) |
| 0028 | agent | 会话与流式：模型目录、思考强度、停止与重连展示 | 当前 | [0028-session-streaming-remainder.md](decisions/0028-session-streaming-remainder.md) |
| 0029 | product | 引用与原文核对：按会话校验，无页码不编造 | 当前 | [0029-citation-and-source-view.md](decisions/0029-citation-and-source-view.md) |
| 0030 | product | DOI / arXiv 标识符导入；无 PDF 保留待补全文 | 当前 | [0030-identifier-import.md](decisions/0030-identifier-import.md) |
| 0031 | product | 端到端验收必须浏览器真实联调，样机与 mock 不算 | 当前 | [0031-e2e-acceptance.md](decisions/0031-e2e-acceptance.md) |
| 0032 | frontend | 界面文案只说状态 / 动作 / 后果；用语表与禁用项 | 当前 | [0032-ui-copy-rules.md](decisions/0032-ui-copy-rules.md) |
| 0033 | frontend | 前端以 web_ui 样式为底座做扩展：上游已有的直接沿用，特有部分在其体系内叠加 | 当前 | [0033-frontend-extend-web-ui.md](decisions/0033-frontend-extend-web-ui.md) |
| 0034 | product | 领域术语与禁用同义词 | 当前 | [0034-domain-glossary.md](decisions/0034-domain-glossary.md) |
| 0035 | security, agent | 原只验签/延迟撤销及否决回查片段由 0081 取代；其余边界保留 | 当前 | [0035-agent-service-access-token-revocation.md](decisions/0035-agent-service-access-token-revocation.md) |
| 0036 | arch, agent | 检索注入与会话范围合并为一个验收里程碑 | 当前 | [0036-merge-retrieval-and-session-scope.md](decisions/0036-merge-retrieval-and-session-scope.md) |
| 0037 | security, api | AgentScope 内部检索请求用独立密钥认证，再查会话绑定授权 | 当前 | [0037-internal-retrieval-authentication.md](decisions/0037-internal-retrieval-authentication.md) |
| 0040 | api, security, frontend | 用户读取会话绑定与已登记引用，前端按 session_id 拼接 | 当前 | [0040-bound-session-read-apis.md](decisions/0040-bound-session-read-apis.md) |
| 0042 | agent, product, ingest | 入读流程完成后增加基于 MinerU Markdown 的有界原文读取工具 | 当前 | [0042-bounded-paper-original-read.md](decisions/0042-bounded-paper-original-read.md) |
| 0043 | api, security, frontend | 会话与项目删除先清理 AgentScope，再清理业务绑定与引用 | 当前 | [0043-bound-session-deletion.md](decisions/0043-bound-session-deletion.md) |
| 0045 | frontend, product | 全局导航保活、单会话工作区、项目文献侧栏、会话草稿与右侧消息快捷栏 | 当前 | [0045-conversation-layout-on-web-ui.md](decisions/0045-conversation-layout-on-web-ui.md) |
| 0049 | product, agent, data, frontend | 定时任务范围、频率、独立运行会话、Agent 创建工具及月视图交互；通知与结果快照片段由 0081 局部取代 | 当前 | [0049-global-schedules-and-weekday-frequency.md](decisions/0049-global-schedules-and-weekday-frequency.md) |
| 0053 | frontend, product | 授权 PDF 用 PDF.js 在页面内渲染并支持引用页定位、翻页与缩放 | 当前 | [0053-embedded-pdf-rendering.md](decisions/0053-embedded-pdf-rendering.md) |
| 0055 | frontend, product | 所有业务弹窗直接沿用 web_ui Dialog 与 Button 的样式 | 当前 | [0055-web-ui-dialog-standard.md](decisions/0055-web-ui-dialog-standard.md) |
| 0056 | ingest, storage, citation | 独立 worker 有界并发、启动恢复；生产 S3 与 MinerU 版本化产物 | 部分失效（0091） | [0056-concurrent-ingestion-artifacts.md](decisions/0056-concurrent-ingestion-artifacts.md) |
| 0057 | frontend, library, ingest | 文献在主区域阅读，右侧按 MinerU 原始 block type 导航与定位 | 块点击交互已被 0066 取代 | [0057-paper-reading-mineru-blocks.md](decisions/0057-paper-reading-mineru-blocks.md) |
| 0058 | frontend, product | 文献处理进度按阶段顺序显示为步骤视图 | 部分失效（0091） | [0058-ingestion-progress-stepper.md](decisions/0058-ingestion-progress-stepper.md) |
| 0059 | frontend, library, product | 文献块显示图片与公式预览，PDF 连续滚动并按可见页绘制 | 当前 | [0059-paper-block-previews-continuous-pdf.md](decisions/0059-paper-block-previews-continuous-pdf.md) |
| 0060 | frontend, library, product | PDF 叠加可选文本层并提供复制菜单；旧 MinerU 图片路径回退，公式优先渲染源码 | 当前 | [0060-paper-text-selection-and-legacy-previews.md](decisions/0060-paper-text-selection-and-legacy-previews.md) |
| 0061 | frontend, library | 文献阅读双栏统一工具栏高度，分块侧栏可拖拽，PDF 支持滚轮及键盘快捷操作 | 当前 | [0061-paper-reading-controls.md](decisions/0061-paper-reading-controls.md) |
| 0062 | frontend, library | 文献信息抽屉不再重复渲染 PDF；阅读页并行加载，图片和图表共用大图查看器 | 当前 | [0062-paper-preview-and-loading.md](decisions/0062-paper-preview-and-loading.md) |
| 0063 | api, library, frontend, cache | 授权文献私有 HTTP 条件缓存与阅读页短时 PDF 热缓存 | 当前 | [0063-private-paper-http-cache.md](decisions/0063-private-paper-http-cache.md) |
| 0066 | frontend, library | 分块只由定位按钮跳转，定位与复制有提示，点击 PDF 空白处取消高亮 | 当前 | [0066-paper-block-locate-action.md](decisions/0066-paper-block-locate-action.md) |
| 0068 | agent, product, storage | AgentScope workspace 仅为运行时字段；新会话 ID 按会话隔离，项目 artifact 以业务项目归属并存对象存储 | 当前 | [0068-workspace-is-not-project-artifact-storage.md](decisions/0068-workspace-is-not-project-artifact-storage.md) |
| 0070 | agent, security, ingest, frontend | 用户确认批量入库、精确标识符 PDF 获取与统一队列 | 当前 | [0070-approved-batch-paper-import.md](decisions/0070-approved-batch-paper-import.md) |
| 0072 | agent, retrieval, frontend, product | 三来源聚合发现与手动在线检索；外部候选不登记 Citation | 当前 | [0072-multi-source-paper-discovery.md](decisions/0072-multi-source-paper-discovery.md) |
| 0075 | agent, frontend, product | Agent 提问由 Questionnaire 接续同一工具调用 | 当前 | [0075-ask-user-questionnaire-and-simple-library-layout.md](decisions/0075-ask-user-questionnaire-and-simple-library-layout.md) |
| 0078 | data, security, agent | 用户偏好与浏览器时区按用户单行存业务库 JSONB；原子局部更新，无对象存储或 Redis | 当前 | [0078-user-settings-jsonb.md](decisions/0078-user-settings-jsonb.md) |
| 0079 | agent, frontend, data, security | 输入框 `@` 资源、`$` Skill、`/` 流程；选中评论统一外层与带类型定位 | 当前 | [0079-composer-references-and-invocations.md](decisions/0079-composer-references-and-invocations.md) |
| 0080 | frontend | SMUI 深浅主题、等宽字体与方角；视觉集中在 token、基础组件与共享 variants | 当前 | [0080-smui-theme.md](decisions/0080-smui-theme.md) |
| 0081 | security, product, agent, data, arch | 邮箱验证与密码找回、Agent 逐请求回查、Redis 临时状态、PG outbox 与可选任务邮件通知；已批准，非验收结论 | 当前 | [0081-email-auth-and-schedule-notifications.md](decisions/0081-email-auth-and-schedule-notifications.md) |
| 0082 | agent, frontend, product | 首条提问并发自动命名会话，仅替换时间戳名称；失败保留原名 | 当前 | [0082-session-auto-naming.md](decisions/0082-session-auto-naming.md) |
| 0083 | agent, product, security, frontend, data | 联网搜索三个读工具、Tavily 单一供应商、Redis 整页缓存、通用服务凭据表与设置页分类导航 | 当前 | [0083-web-search-and-fetch.md](decisions/0083-web-search-and-fetch.md) |
| 0084 | frontend | 会话公式开启单美元行内语法，块级公式沿用双美元；锁定兼容的样式转换依赖 | 当前 | [0084-chat-math-rendering.md](decisions/0084-chat-math-rendering.md) |
| 0085 | ingest, agent, frontend | 行间公式与图片进入正文、单一截断点、引用定位改为拍平块列表并由前端消费 | 当前 | [0085-parsing-fidelity-and-citation-locating.md](decisions/0085-parsing-fidelity-and-citation-locating.md) |
| 0086 | retrieval, ingest, deployment | 平台统一自部署 bge-large、英文工具查询、单层请求分批、有界重试与精简检索状态；自部署部分已被 0087 取代 | 已被 0087 局部取代 | [0086-self-hosted-embedding.md](decisions/0086-self-hosted-embedding.md) |
| 0087 | ingest, deployment, retrieval | MinerU 与 Embedding 都改回远程服务；本机不跑模型容器，bge-m3 1024 维并重置向量 | 当前 | [0087-remote-parsing-and-embedding.md](decisions/0087-remote-parsing-and-embedding.md) |
| 0088 | retrieval, security, ingest | 入库向量化平台付费、检索 query 向量用用户自带 Key；无 Key 时降级为纯关键词 | 当前 | [0088-paid-ingestion-byok-search.md](decisions/0088-paid-ingestion-byok-search.md) |
| 0089 | agent, security | 强制关闭文件 offloader 和目录提示，保留内建压缩；修正无能力工作区隔离与生命周期 | 当前 | [0089-no-file-offloader.md](decisions/0089-no-file-offloader.md) |
| 0090 | security, retrieval, ingest | 上游错误不进响应/错误记录/日志，请求级只覆盖 read 超时；检索设置明确 SiliconFlow Key | 当前 | [0090-safe-embedding-errors.md](decisions/0090-safe-embedding-errors.md) |
| 0091 | library, ingest, data | 文献独占书目一份、条目只存归属；文献必带原文；阶段名对应产物（metadata/parse/chunking/embedding） | 当前 | [0091-papers-own-bibliographic-facts.md](decisions/0091-papers-own-bibliographic-facts.md) |
| 0092 | ingest, data, product | 一次入库=一条 paper_imports、一篇一条；四阶段 source/parse/chunk/embed；元数据不占流程；未完成不进列表 | 已被 0094 取代 | [0092-import-is-one-flow.md](decisions/0092-import-is-one-flow.md) |
| 0093 | data, ingest, storage, frontend | 删 user_papers.source 等无读取方的字段；产物改按 file_hash 扁平覆盖写；错误文案只由后端提供 | 当前 | [0093-column-pruning-and-flat-artifact-paths.md](decisions/0093-column-pruning-and-flat-artifact-paths.md) |
| 0094 | data, ingest, product | 下载(downloads)与处理(runs)分成两条记录；下载异步、按用户建行不按 URL 去重；阶段并入 runs；删 user_papers.ready；界面合并为一个队列 | 当前 | [0094-download-and-run-are-separate-stages.md](decisions/0094-download-and-run-are-separate-stages.md) |
| 0095 | data, ingest, product, frontend | 队列合并 downloads 与 user_runs，仅消除跨表重复并保留历史 run；项目归属随请求，成功授权原子提交；列表看状态、详情看步骤 | 当前 | [0095-queue-is-requests-not-downloads.md](decisions/0095-queue-is-requests-not-downloads.md) |
| 0096 | ingest, data, arch | 领取粒度改为阶段，各阶段独立并发；阶段失败按次数指数退避后自动重试；重试计数与退避时间存 runs 并随状态同事务 | 当前 | [0096-stage-level-concurrency.md](decisions/0096-stage-level-concurrency.md) |

状态取值：`当前` / `已被 NNNN 取代` / `已废弃`；合并来源见下表，原文仍可从 Git 历史读取。
标签：`ingest` / `agent` / `arch` / `security` / `api` / `data` / `product` / `frontend`

### 合并来源

| 当前决策 | 已并入的旧编号 |
|---|---|
| 0006 | 0002、0005 |
| 0015 | 0004、0038、0039 |
| 0026 | 0041 |
| 0043 | 0044 的项目删除部分 |
| 0045 | 0064、0067、0071、0076 的导航部分；0075 的侧栏部分 |
| 0049 | 0017、0046–0048、0050–0052 |
| 0055 | 0054 |
| 0056 | 0012、0044 的 worker 部分 |
| 0063 | 0065 |
| 0070 | 0074、0077、0076 的队列部分 |
| 0072 | 0069、0073 |

按触发场景找：

| 触发场景 | 读哪一组 |
|---|---|
| 改动 Agent 后端、会话、检索或凭据接入 | 0006、0007–0016 中相关项、0015、0026、0035–0037、0049、0070、0072、0075、0078 |
| 改动产品功能范围、文献 / 摄取 / 引用行为 | 0018–0034 中相关项、0049、0056–0063、0070、0072 |
| 改前端文案或界面 | 0014、0032、0033、0045、0049、0055、0080；文献阅读见 0057–0066 |
| 改邮箱认证、密码重置、登录态回查或任务邮件通知 | 0081（0022、0035、0049 仅相关片段被取代） |
| 涉及领域术语与命名 | 0034 |
| 改包结构、入口或依赖方向 | [ARCHITECTURE.md](ARCHITECTURE.md) 与 0003、0006 |

`docs/` 的入口为 [ARCHITECTURE.md](ARCHITECTURE.md)、`DECISIONS.md`、`decisions/`、[调研分类索引](research/README.md)。

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
- 日常取舍变化新建决策并标注 SUPERSEDES；用户明确要求合并整理时可把同主题旧条目并入当前决策，索引登记旧编号并从 Git 历史保留原文。
- 单文件尽量 ≤40 行；主题合并以完整保留有效约束和重要否决理由为先。
- 只有影响后续取舍的才值得记。改个变量名不用记。
- 2026-09 之前的历史决策原文已删除，结论保留在 `0001` 及 0018–0034；推翻它们时新建条目并标注 SUPERSEDES。
