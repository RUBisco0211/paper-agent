# 实施状态（本轮）

日期：2026-09-17。对应功能规格：[minimal-mvp.md](minimal-mvp.md)。本文只记录**当前代码实际提供的能力**与**明确后置的部分**，不修改功能契约。

## 1. 后端已落地

| 功能 | 状态 | 对应接口 |
|---|---|---|
| F01 账号与登录态 | 已实现 | `POST /v1/auth/register\|login\|refresh\|logout`、`GET /v1/auth/me` |
| F02 上传与个人论文库 | 已实现 | `POST/GET /v1/papers`、`GET /v1/papers/{id}`、`GET /v1/papers/{id}/pdf` |
| F03 解析、元数据与重试 | 已实现（解析器依赖实例配置） | `GET /v1/ingestion-jobs/{id}`、`POST .../retry`、`POST /v1/papers/{id}/resolve-metadata` |
| F04 项目与问答范围 | 已实现 | `/v1/projects`、`/v1/projects/{id}/papers` |
| F05 检索与 Agent 论文工具 | 检索已实现；Agent 工具未接入 | `POST /v1/search` |
| F06 会话与流式回答 | 会话机制已实现；LLM 执行未接入 | `/v1/sessions/*`（含 `events`、`messages`、`stop`、`resume`） |
| F07 阅读原文与验证引用 | 已实现 | `GET /v1/sessions/{id}/citations/{citation_id}` |
| F08 DOI/arXiv 导入 | 已实现（依赖来源可用性） | `POST /v1/imports`、`GET /v1/imports/{id}` |
| F09 仅元数据条目 | 已实现 | 条目先有身份，拿到 PDF 后绑定共享 Paper |

已落地的基础设施：

- SQLAlchemy 2.0（同步）+ Alembic 迁移（`20260917_0001`–`20260917_0006`）；
- PostgreSQL 16 + pgvector：`tsvector` 生成列 + GIN 索引、`vector(1536)` 余弦距离；
- structlog + 标准库 logging、`X-Request-ID` 关联、统一错误契约（稳定错误码 + request_id）；
- 对象存储抽象与本地实现（PDF、MinerU 产物、会话 Entry JSONL）；
- 进程内任务调度器（`AsyncioTaskScheduler`），测试使用 `InlineTaskScheduler`。

## 2. 明确未接入（不是“已完成”）

| 项目 | 当前行为 | 影响 |
|---|---|---|
| Agent 回合执行 | `UnconfiguredAgentRunner` 返回稳定错误 `agent_unavailable`，并写入 `stop_reason=failed` 的 assistant Entry | 会话机制、pending 队列、SSE、引用校验均可测；真实回答需要接入 AgentScope 执行器 |
| MinerU 正文解析 | 未配置 `MINERU_API_URL` 时 fulltext 阶段失败并记录 `provider_not_configured`，作业状态 `failed` | 本地识别、元数据补全与条目状态仍可用 |
| Embedding | 未配置时 embedding 阶段失败，`has_keyword_index=true`、`has_embedding=false` | 检索为 degraded（仅关键词通道），不会伪装成混合检索 |
| Redis / Celery / MinIO | 未引入；后台任务在 FastAPI 进程内、Entry 日志写本地对象存储 | 单机单进程语义；重启后活动生成中断（pending 仍保留） |
| 前端页面 | 已实现登录/注册、论文库、项目、会话工作区与模型设置 | 见第 3 节；`/v1/search` 暂无独立页面（按规格不做搜索页） |

## 3. 前端页面（已实现）

| 路由 | 对应功能 | 主要交互 |
|---|---|---|
| `/login`、`/register` | F01 | 登录/注册、字段级校验、登录后回到原目标页 |
| `/library` | F02/F03/F08 | 上传 PDF、DOI/arXiv 导入、按标题过滤、分页、能力与处理状态分列、处理中自动轮询 |
| `/library`（详情抽屉） | F03/F07 | 阶段表与失败重试、补传 PDF、重新获取全文、补全/修正元数据、内嵌 PDF 阅读、加入项目、就用这篇提问 |
| `/projects`、`/projects/:id` | F04 | 创建/改名/删除项目、从个人库多选添加、按标识符导入到项目、项目会话列表 |
| `/sessions`、`/sessions/:id` | F06/F07 | 范围筛选、新建/改名/删除会话、流式回答、steering/follow-up 入队、停止、继续处理队列、引用展开证据 |
| `/settings` | LLM 配置 | Provider 允许列表、模型与 API Key 存浏览器本地，并说明数据流向 |

前端校验现状：`pnpm run test` 20 个用例（API 客户端、SSE 解析、聊天组件语义、应用启动），`pnpm run typecheck` 与 `pnpm run build` 通过。

## 4. 端到端可验证路径

```bash
docker compose up -d postgres
cd backend && uv sync && cp .env.example .env && uv run alembic upgrade head
uv run pytest -q          # 95 个用例：契约、隔离、并发与故障语义
uv run uvicorn app.main:app --port 8000

cd ../frontend && pnpm install && pnpm run test && pnpm run typecheck && pnpm dev
# 浏览器打开 http://127.0.0.1:5173（/v1 由 Vite 代理转发到后端）
```

手写联调可参考 `uv run python main.py` 后的 `/docs`（OpenAPI），关键场景：

1. 注册 → 上传 PDF → `GET /v1/papers/{id}` 看到能力与阶段；
2. 上传 `arXiv:1706.03762` 文本的 PDF → metadata 阶段识别并补全（需要在线来源可用）；
3. `POST /v1/imports` 导入 DOI/arXiv，观察 `ready` 与 `pdf_unavailable` 两种终态；
4. 用两个账号互相访问对方的论文 / PDF / 项目 / 会话 / 引用，均应返回 404。

## 5. 未覆盖的验收点

- 真实 LLM 问答与工具摘要的浏览器闭环：页面已具备，但执行器仍返回 `agent_unavailable`，因此只验证到“失败可解释”；
- 引用展开页面已实现，但没有真实回答产生引用（依赖 Agent 接入后写入证据）；
- MinerU 真实产物校验与解析质量（需要实例级凭据）；
- 多用户并发上传同一 PDF 的全局锁竞争（当前依赖唯一约束与幂等写入，未做 Redis 锁）；
- 浏览器端到端用例（Playwright）与 Yaak 集合。
