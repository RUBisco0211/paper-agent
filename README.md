# Paper Agent

Paper Agent 管理个人论文库、项目范围和基于论文证据的 Agent 阅读会话。它是多用户系统，但每个用户的数据与交互彼此隔离。

本仓库同时交付后端 API 与 React 前端：

```text
backend/    FastAPI 模块化单体后端（另有独立的 README）
frontend/   React + TypeScript + shadcn/ui 前端
docs/       产品契约、架构基线与技术选型调研
```

## 文档

| 文档 | 内容 |
|---|---|
| [docs/overview/minimal-mvp.md](docs/overview/minimal-mvp.md) | 本轮 MVP 功能规格与验收标准（功能范围以此为准） |
| [docs/overview/prototype.md](docs/overview/prototype.md) | 领域模型、数据模型与架构基线 |
| [docs/infrastructure/technical-stack-research.md](docs/infrastructure/technical-stack-research.md) | ORM、日志、中间件选型 |
| [docs/infrastructure/sse-architecture-research.md](docs/infrastructure/sse-architecture-research.md) | SSE 传输与事件模型 |
| [docs/infrastructure/logging-conventions.md](docs/infrastructure/logging-conventions.md) | 日志事件命名与字段约定 |
| [docs/overview/implementation-status.md](docs/overview/implementation-status.md) | 当前已实现范围与明确未接入的部分 |
| [docs/frontend/ui-spec.md](docs/frontend/ui-spec.md) | 前端文案、布局与 shadcn 组件规范（改前端前必读） |
| [CONTEXT.md](CONTEXT.md) | 领域术语表（ubiquitous language） |
| [AGENTS.md](AGENTS.md) | 协作约定与必读文档索引 |
| [.env.example](.env.example) | compose 变量（HF 端点、TEI 镜像、向量模型） |

## 快速开始

需要 Python 3.13、[uv](https://docs.astral.sh/uv/)、Node.js 22+ 与 pnpm。

```bash
# 1. 依赖服务（PostgreSQL 16 + pgvector）
docker compose up -d postgres

# 可选：向量检索所需的 Embedding 服务（TEI + BAAI/bge-m3，首次拉镜像与权重）
# 直连 huggingface.co 不通时，在仓库根 .env 里设 HF_ENDPOINT=https://hf-mirror.com
cp .env.example .env
docker compose up -d embedding

# 2. 后端
cd backend
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run python main.py          # http://127.0.0.1:8000

# 3. 前端
cd ../frontend
pnpm install
pnpm dev                       # http://127.0.0.1:5173
```

## 验证

```bash
# 后端：契约、鉴权隔离、处理流水线、检索与队列语义
cd backend && uv run pytest -q          # 95 passed

# 前端：类型检查、组件与启动路径
cd frontend && pnpm run typecheck && pnpm run test   # 20 passed
```

接口文档在服务启动后访问 <http://127.0.0.1:8000/docs>（OpenAPI）。浏览器端已实现登录/注册、论文库（上传、DOI/arXiv 导入、
详情与内嵌 PDF）、项目、会话工作区（流式回答、排队输入、停止/继续、引用展开）与模型设置。

当前实现范围与明确未接入的部分见
[docs/overview/implementation-status.md](docs/overview/implementation-status.md)：会话与流式机制、pending 队列、
引用校验都已落地，但真正执行 LLM 的 Agent 回合仍是一个显式返回 `agent_unavailable` 的桩，因此浏览器里能看到
“失败可解释”而不是伪造回答。

## 数据流向

为了让回答可用，系统会把数据发给外部服务：PDF 发往 MinerU 解析正文；Chunk 文本发往 Embedding 服务生成向量；用户问题与检索到的论文证据发往用户自己配置的 LLM Provider。LLM API Key 只驻留执行器内存，不写入数据库、日志、对象存储或任务队列。
