# 实施状态

日期：2026-09-19。对应功能规格：[minimal-mvp.md](minimal-mvp.md)。本文只记录**当前代码实际提供的能力**与**明确后置的部分**，不修改功能契约。

## 1. 功能清单（对照规格编号）

| 功能 | 状态 | 对应接口 |
|---|---|---|
| F01 账号与登录态 | 已实现：注册、登录、刷新轮换、登出、当前用户；Argon2id、JWT（`jti` + 重放撤销 token family）、Origin 校验 | `POST /v1/auth/register\|login\|refresh\|logout`、`GET /v1/auth/me` |
| F02 上传与个人论文库 | 已实现：magic/大小/页数校验、SHA-256 全局去重、列表/详情/PDF 流 | `POST/GET /v1/papers`、`GET /v1/papers/{id}`、`GET /v1/papers/{id}/pdf` |
| F03 解析、元数据与重试 | 已实现：四阶段状态机（metadata/fulltext/chunking/embedding）、阶段级重试、补传 PDF、抓取全文、补全/修正元数据 | `GET /v1/ingestion-jobs/{id}`、`POST .../retry`、`POST /v1/papers/{id}/fetch-metadata`、`POST /v1/papers/{id}/fetch-pdf`、`PATCH /v1/papers/{id}/info` |
| F04 项目与问答范围 | 已实现：项目 CRUD、项目论文只增不减、删除项目级联清理其会话 | `/v1/projects`、`/v1/projects/{id}/papers` |
| F05 检索与 Agent 论文工具 | 已实现：关键词 + 向量双通道召回、RRF 融合、每篇配额；**三个只读工具已接入 Agent** | `POST /v1/search` |
| F06 会话与流式回答 | 已实现：会话 CRUD、JSONL Entry 日志、消息/pending 双队列、停止/继续、SSE（`Last-Event-ID` 重放）、范围注入、**AgentScope 真实执行** | `/v1/sessions/*`（`entries`、`events`、`messages`、`stop`、`resume`） |
| F07 阅读原文与验证引用 | 已实现：引用展开原文片段与页码，落库校验会话归属 | `GET /v1/sessions/{id}/citations/{citation_id}` |
| F08 DOI/arXiv 导入 | 已实现：先元数据后尝试全文，两种终态（`ready` / `pdf_unavailable`） | `POST /v1/imports`、`GET /v1/imports/{id}` |
| F09 仅元数据条目 | 已实现：条目先有身份，拿到 PDF 后绑定共享 Paper | 与 F03 同 |

## 2. Agent 回合执行（已接入）

`GET /v1/llm-catalog` 从 AgentScope Model Card 返回 Provider、active 模型及其思考强度档位。设置页只允许选择目录项并填写 API Key；
后端再次校验组合后创建对应的 AgentScope 原生模型，客户端不能提交 Base URL。

三个只读工具（`app/sessions/tools.py`），**范围由会话上下文注入，模型无法通过参数越权**：

| 工具 | 作用 |
|---|---|
| `list_papers` | 列出会话范围内的文献与可用能力 |
| `search_papers` | 混合检索、登记 Citation、返回可引用证据 |
| `get_paper_excerpt` | 按 `citation_id` 展开原文片段与页码（再校验会话归属） |

回合语义：

- 模型输出映射为稳定事件（文本增量、工具开始/结束、用量、终态），工具输出摘要先落 `tool_result` Entry，
  中止或失败也能看到做了什么；回答携带的 citation_id 写入 Assistant Entry，前端据此渲染可点击引用；
- 失败一律折成稳定错误码：`llm_not_configured`（401/403）、`provider_rate_limited`（429）、
  `agent_timeout`、`agent_max_iters`（默认 8 轮）、`agent_unavailable`；`AGENT_TURN_TIMEOUT_SECONDS` 默认 240s；
- LLM Key 只随启动或恢复请求进入当前执行器，不落库、不进日志、不进对象存储；
- 事件映射与落库均有离线用例（假 Agent / 假仓储）；**真实 LLM 的浏览器闭环尚未验收**（见第 7 节）。

## 3. 检索与 Embedding

- 适配层 `EmbeddingAdapter` + 模型档案：换模型/换服务是配置变更（13 个档案覆盖 bge 系、e5、nomic、
  embeddinggemma、qwen3、OpenAI 与 DashScope 的 text-embedding-*）；
- 当前指向 DashScope `text-embedding-v3`（1024 维）。**已用真实服务验证**：单条与批量调用均返回 1024 维；
- **混合检索已用真实数据验证**：同一查询下关键词 1 条 + 向量 20 条候选，RRF 融合后给出 3 条带页码证据；
- 未配置或调用失败时检索退化为仅关键词，并在响应里标明，不伪装成混合检索；
- `chunks.embedding = vector(1024)`，启动时自检配置维度与列维度是否一致（`configuration.embedding_dimension_mismatch`）。

## 4. 对象存储

`app/platform/storage.py` 的 `ObjectStorage` 接口 + 两种实现，Key 布局一致，换后端是配置变更：

| 后端 | 说明 |
|---|---|
| `local`（默认） | 写 `STORAGE_ROOT`（默认 `.var/storage`），单机挂卷即可；`materialize()` 零拷贝给出真实路径 |
| `s3` | 任何 S3 兼容服务（本地 RustFS / Garage / 云对象存储）；大文件分片上传，`materialize()` 下载到临时文件并清理 |

- 保存内容：PDF 原文、MinerU 原始产物（`content_list.json` / `full.md` / 图片）、会话 Entry JSONL；
- 一致性由共享协议用例保证：同一组用例跑在 local、模拟 S3 与真实 RustFS 上；整套后端用例也可整体跑在
  `PAPER_AGENT_LIVE_STORAGE=1` 指向的真实对象存储上；
- 启动自检 `configuration.storage_ready`（顺带创建缺失的 bucket）。

## 5. 前端页面

| 路由 | 对应功能 | 主要交互 |
|---|---|---|
| `/login`、`/register` | F01 | 登录/注册、字段级校验、登录后回到原目标页 |
| `/library` | F02/F03/F08 | 上传 PDF、DOI/arXiv 导入、按标题过滤、分页、能力与处理状态分列、处理中自动轮询 |
| `/library`（详情抽屉） | F03/F07 | 阶段表与失败重试、补传 PDF、重新获取全文、补全/修正元数据、内嵌 PDF 阅读、加入项目、就用这篇提问 |
| `/projects`、`/projects/:id` | F04 | 创建/重命名/删除项目、从个人库多选添加、按标识符导入到项目、项目会话列表 |
| `/sessions/:id` | F06/F07 | 用户消息气泡、支持 GFM/公式与流式未闭合语法的 Agent 正文、可折叠 Thinking、紧凑工具调用状态、PDF 上传、模型与思考强度切换、steering/follow-up 入队、停止、继续处理队列与引用展开（会话列表和新建入口在侧边栏按范围分组） |
| `/settings` | LLM 配置 | 从 AgentScope 目录选择 Provider/模型，只输入 API Key |

界面规范见 [ui-spec.md](../frontend/ui-spec.md)：统一 `PageHeader`、侧边栏范围分组与折叠、状态配色、
动效约定、shadcn 官方组件。

当前校验：前端 45 个用例、类型检查与生产构建通过；后端 170 个用例通过、1 个跳过。

## 6. 基础设施

- SQLAlchemy 2.0（同步）+ Alembic（`20260917_0001`–`20260917_0007`）；
- PostgreSQL 16 + pgvector：`tsvector` 生成列 + GIN 索引、`vector(1024)` 余弦距离；
- structlog + 标准库 logging、`X-Request-ID` 关联、统一错误契约（稳定错误码 + request_id）；
- 进程内任务调度器（`AsyncioTaskScheduler`），测试用 `InlineTaskScheduler`；
- 部署配置自检：弱 JWT 密钥、Embedding 维度不匹配、对象存储不可用都会在启动时以稳定事件名报出；
- `docker-compose.yml` 提供 Postgres、可选 TEI（`profile: embeddings`）、可选 RustFS（`profile: storage`）；
  `./start.sh` 按 `backend/.env` 与实际配置自动拉起所需容器。

## 7. 尚未验收 / 明确后置

| 项目 | 现状 |
|---|---|
| 真实 LLM 的端到端问答 | 执行器、工具、事件映射与落库均有离线用例；**尚未用真实 LLM Key 跑通「提问 → 工具 → 带引用的回答」的浏览器闭环** |
| 多实例部署 | 后台任务在进程内执行，重启会中断正在进行的生成（pending 仍保留）；会话与文献不做数据库关联，范围写在 Entry 日志里 |
| 自建 Embedding | 自建 TEI 的 bge-m3 权重已下载并校验（`./models/bge-m3`），因本机内存不足未加载；本机先用云 Embedding |
| 历史处理失败 | 早期缺少 Provider 配置时留下的失败任务需要逐个重试（文献详情抽屉里可重试）；旧任务不会自动补跑 |
| 并发上传同一 PDF | 依赖唯一约束与幂等写入，未做跨进程锁 |
| 浏览器端到端用例 | Playwright 与 Yaak 集合尚未建立 |
| 未提供的入口 | 按规格不提供「从项目移除文献」「删除文献」；`/v1/search` 无独立页面 |

## 8. 本地跑起来与自检

```bash
docker compose up -d postgres          # 需要 S3 存储时追加：--profile storage up -d storage
./start.sh                             # 数据库 + 后端 + 前端（Ctrl-C 全部停止）

cd backend && uv run pytest -q         # 170 passed, 1 skipped（需 Postgres）
PAPER_AGENT_LIVE_STORAGE=1 uv run pytest -q   # 整套跑在 backend/.env 指向的真实对象存储上

cd ../frontend && pnpm run test && pnpm run typecheck && pnpm run build
```

浏览器打开 `http://127.0.0.1:5173`（`/v1` 由 Vite 代理到后端）。关键联调场景：

1. 注册 → 上传 PDF → `GET /v1/papers/{id}` 看到能力与阶段，详情抽屉里可重试失败阶段；
2. 上传含 `arXiv:1706.03762` 文本的 PDF → metadata 阶段识别并在线补全；
3. `POST /v1/imports` 导入 DOI/arXiv，观察 `ready` 与 `pdf_unavailable` 两种终态；
4. 在 `/settings` 选择 Provider/模型并填写 API Key → 新建会话提问，观察工具调用、流式回答与可点击引用；
5. 用两个账号互相访问对方的论文 / PDF / 项目 / 会话 / 引用，均应返回 404。
