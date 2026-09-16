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
| 前端页面 | 未实现；仅提供类型化 API 客户端与 SSE 适配 | 页面层可直接基于 `frontend/src/lib/api` 构建 |

## 3. 端到端可验证路径

```bash
docker compose up -d postgres
cd backend && uv sync && cp .env.example .env && uv run alembic upgrade head
uv run pytest -q          # 94 个用例：契约、隔离、并发与故障语义

cd ../frontend && pnpm install && pnpm run test && pnpm run typecheck
```

手写联调可参考 `uv run python main.py` 后的 `/docs`（OpenAPI），关键场景：

1. 注册 → 上传 PDF → `GET /v1/papers/{id}` 看到能力与阶段；
2. 上传 `arXiv:1706.03762` 文本的 PDF → metadata 阶段识别并补全（需要在线来源可用）；
3. `POST /v1/imports` 导入 DOI/arXiv，观察 `ready` 与 `pdf_unavailable` 两种终态；
4. 用两个账号互相访问对方的论文 / PDF / 项目 / 会话 / 引用，均应返回 404。

## 4. 未覆盖的验收点

- 真实 LLM 问答、工具摘要与“引用能回到原文”的浏览器闭环（依赖第 2 节的 Agent 接入）；
- MinerU 真实产物校验与解析质量（需要实例级凭据）；
- 多用户并发上传同一 PDF 的全局锁竞争（当前依赖唯一约束与幂等写入，未做 Redis 锁）；
- 浏览器端到端用例（Playwright）与 Yaak 集合。
