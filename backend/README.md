# Paper Agent Backend

Paper Agent 的 FastAPI 模块化单体后端：负责账号与登录态、个人论文库、项目范围、论文处理流水线、混合检索与 Agent 会话。

功能契约见 [../docs/overview/minimal-mvp.md](../docs/overview/minimal-mvp.md)，架构基线见 [../docs/overview/prototype.md](../docs/overview/prototype.md)，技术选型见 [../docs/infrastructure/technical-stack-research.md](../docs/infrastructure/technical-stack-research.md)。

## 本地依赖

- Python 3.13（由 `.python-version` 固定，`uv` 会自动安装）
- PostgreSQL 16 + pgvector（`docker compose up -d postgres`，见仓库根目录 `docker-compose.yml`）

## 启动

```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run python main.py
```

服务启动后可访问：

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

## 测试

集成测试直接连接真实 PostgreSQL（用到 pgvector 与全文检索）：:

```bash
docker compose -f ../docker-compose.yml up -d postgres
uv run pytest
```

测试默认使用 `DATABASE_URL` 指向的库，并通过 `TEST_DATABASE_URL` 覆盖。

## 目录结构

```text
app/
├── platform/     # 横切设施：配置、数据库、日志、错误、存储、安全
├── auth/         # 账号、登录态与刷新令牌轮换
├── library/      # 个人论文库条目、PDF 上传与元数据
├── projects/     # 项目与项目论文范围
├── ingestion/    # 处理任务、阶段状态与解析适配器
├── retrieval/    # Chunk、混合检索与 RRF
├── sessions/     # 会话、Entry、pending 队列、SSE 与引用
├── imports/      # DOI/arXiv 标识符导入
└── main.py       # FastAPI 应用装配
alembic/          # 版本化数据库迁移
tests/            # 单元测试与 PostgreSQL 集成测试
```

每个领域模块沿用仓库既有的垂直切片：`domain.py`（领域规则）、`application.py`（用例编排）、`api.py`（HTTP 适配器）、`persistence.py`（SQLAlchemy 仓储），`platform/` 只放跨领域技术设施。

## 接口一览

| 领域 | 接口 |
|---|---|
| 认证 | `POST /v1/auth/register\|login\|refresh\|logout`、`GET /v1/auth/me` |
| 论文库 | `POST/GET /v1/papers`、`GET /v1/papers/{paper_id}`、`GET /v1/papers/{paper_id}/pdf` |
| 补全文 | `POST /v1/papers/{paper_id}/pdf`、`POST /v1/papers/{paper_id}/fetch-pdf` |
| 元数据 | `PATCH /v1/papers/{paper_id}/metadata`、`POST /v1/papers/{paper_id}/resolve-metadata` |
| 处理任务 | `GET /v1/ingestion-jobs/{job_id}`、`POST /v1/ingestion-jobs/{job_id}/retry` |
| 项目 | `/v1/projects`、`/v1/projects/{project_id}`、`GET/POST /v1/projects/{project_id}/papers` |
| 会话 | `/v1/sessions`、`GET /v1/sessions/{session_id}/entries` |
| 生成 | `POST /v1/sessions/{session_id}/messages\|stop\|resume`、`GET /v1/sessions/{session_id}/events` |
| 引用 | `GET /v1/sessions/{session_id}/citations/{citation_id}` |
| 检索 | `POST /v1/search`（library / project / paper 三种授权范围） |
| 导入 | `POST /v1/imports`、`GET /v1/imports/{import_id}` |

所有错误统一为 `{"code", "message", "request_id"}`；`code` 是稳定的 snake_case 字符串。上传、消息与重试类操作
都会校验归属，越权访问统一按“不存在”处理。

## Provider 配置说明

`MINERU_API_URL` 只填 **base URL**（例如 `https://mineru.net`）：适配器会自行拼接
`/api/v4/file-urls/batch`（申请上传地址）与 `/api/v4/extract-results/batch/{batch_id}`（轮询结果）。
把某个具体端点写进这个变量会拼出不存在的地址，阶段会以 `provider_unavailable` 失败。

用测试时不需要这些凭据：集成测试会在会话内清空 Provider 配置，避免用例依赖本地 `.env`。

## 当前未接入的能力

- AgentScope 执行器：会话、pending 队列、SSE 与引用都已实现，但执行器仍返回 `agent_unavailable`，不会伪造回答；
- MinerU / Embedding：未配置时对应阶段失败并记录 `provider_not_configured`，已完成的阶段能力继续可用；
- Redis / Celery / MinIO：后台任务在进程内执行，Entry 日志写本地对象存储，适合单机单进程。

## 日志

日志使用 `structlog`，底层统一走标准库 `logging`。默认输出开发态可读文本，`LOG_JSON=true` 输出单行 JSON；每个请求会返回并记录 `X-Request-ID`。约定见 [../docs/infrastructure/logging-conventions.md](../docs/infrastructure/logging-conventions.md)。

## 数据流向

为了产出可用回答，系统会把数据发给外部服务：

- PDF 发往 MinerU 解析正文；
- Chunk 文本发往 Embedding 服务生成向量；
- 用户问题与检索到的论文证据发往用户自己配置的 LLM Provider。

LLM API Key 只驻留当前执行器内存，不写入数据库、日志、对象存储或队列。MinerU 与 Embedding 为实例级配置，由部署者通过环境变量固定。
