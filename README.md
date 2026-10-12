# Paper Agent

Paper Agent 管理个人论文库、项目范围和基于论文证据的 Agent 阅读会话。它是多用户系统，但每个用户的数据与交互彼此隔离。

本仓库同时交付后端 API 与 React 前端：

```text
backend/    FastAPI 模块化单体后端（另有独立的 README）
frontend/   React + TypeScript + shadcn/ui 前端
docs/       产品契约、架构基线、决策记录与调研
```

## 文档

| 文档 | 内容 |
|---|---|
| [AGENTS.md](AGENTS.md) | AI 协作的唯一常驻约束（改代码前必读） |
| [WORKFLOW.md](WORKFLOW.md) | 给人看的流程总纲：任务分档、七阶段与检查点 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 前后端运行入口、包结构和依赖边界 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 决策索引（正文一条一文件） |
| [docs/research/technical-stack.md](docs/research/technical-stack.md) | ORM、日志、中间件选型 |
| [docs/research/sse-transport.md](docs/research/sse-transport.md) | SSE 传输与事件模型 |
| [docs/research/llm-model-catalog.md](docs/research/llm-model-catalog.md) | 模型目录与 LLM 请求层选型 |
| [docs/research/agentero-paper-workflow.md](docs/research/agentero-paper-workflow.md) | 论文解析、元数据与 Agent 工具调研 |
| [docs/research/ai-development-workflows.md](docs/research/ai-development-workflows.md) | AI 辅助开发的规范与进度管理调研 |
| [.env.example](.env.example) | compose 变量（HF 端点、TEI 镜像、向量模型） |

按场景找决策：`docs/DECISIONS.md` 底部有「按触发场景找」的对照表。

## 快速开始

需要 Python 3.13、[uv](https://docs.astral.sh/uv/)、Node.js 22+、pnpm 与 Docker。

```bash
./start.sh  # PostgreSQL、业务服务 :8000、解析 worker、AgentScope :8001、前端 :5173
```

## 验证

```bash
# 后端：契约、鉴权隔离、处理流水线、检索与队列语义
cd backend && uv run pytest -q

# 前端：类型检查、组件与启动路径
cd frontend && pnpm run typecheck && pnpm run test && pnpm run build
```

接口文档在服务启动后访问 <http://127.0.0.1:8000/docs>（OpenAPI）。浏览器端已实现登录/注册、论文库（上传、DOI/arXiv 导入、
详情与内嵌 PDF）、按项目分组的对话、定时任务月视图、AgentScope 模型凭据设置和会话工作区（流式回答、工具状态与引用原文）。定时任务可选全局或项目范围，自定义提示词与一周内的执行日；历次运行在任务详情中查看，不进入普通会话列表。

功能范围与验收标准见 `docs/DECISIONS.md` 的 0018–0034 一组（原功能规格文档已拆为决策条目）。
AgentScope 服务、会话绑定、库内文献工具、库外文献发现和引用回查已接入；旧会话执行链已移除，文献解析由独立 worker 消费数据库任务。DeepSeek 浏览器主路径已验证，用户确认 R8 无待处理问题；已验证范围及未留存逐项记录的边界见 [TODO.md](TODO.md) 的 R8。

## 数据流向

为了让回答可用，系统会把数据发给外部服务：PDF 发往 MinerU 解析正文；Chunk 文本发往 Embedding 服务生成向量；用户问题与检索到的文献证据发往用户选择的 LLM Provider。LLM API Key 由 AgentScope Credential 服务加密保存，不写入日志、对象存储或任务队列。
