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
| [docs/research/README.md](docs/research/README.md) | 分类调研索引：AgentScope、SMUI、平台技术、LLM、文献工作流与 AI 开发 |
| [backend/.env.example](backend/.env.example) | 后端环境变量示例；根 `.env` 单独保留 Compose 有效配置，不提交真实凭据 |

按场景找决策：`docs/DECISIONS.md` 底部有「按触发场景找」的对照表。

## 快速开始

需要 Python 3.13、[uv](https://docs.astral.sh/uv/)、Node.js 22+、pnpm 与 Docker。

```bash
./start.sh  # PostgreSQL、Redis、业务服务 :8000、解析/邮件 worker、AgentScope :8001、前端 :5173
```

## 邮件部署与配置边界

- 根 `.env` 继续供 Compose 插值（数据库密码、TEI/HF、RustFS 等），不要删除或与 `backend/.env` 合并；数据库密码须与后端连接串一致。
- `backend/.env` 供业务服务、AgentScope 与 worker 使用。邮件需配置 `REDIS_URL`、`PUBLIC_APP_URL` 和独立 SMTP 参数，详见 [后端部署说明](backend/README.md#邮箱认证与任务通知部署)。QQ SMTP 授权码只由主 agent 写入该未提交文件，不进入文档、日志或示例。
- Redis 镜像 `redis:7-alpine` 使用标准 `6379`（容器内与本机映射一致）；本机不得再运行第二个 Redis，应用不得连接宿主机 Redis。默认不持久化，临时状态丢失后须重新验证。邮件 outbox 持久存 PostgreSQL，不使用 Celery。
- `start.sh` 启动并校验 Compose Redis：发布端口必须等于 `REDIS_HOST_PORT`，且宿主机端口连接的 `run_id` 必须与容器一致；校验失败直接退出，不会回退到宿主机 Redis。脚本同时管理 `python -m app.platform.mail_worker` 的生命周期与 `.var/logs/mail-worker.log`；任一服务进程退出会触发 cleanup。Ctrl-C 停止脚本启动的进程，Compose 容器与数据库保留；`--skip-db` 不跳过 Redis，`--frontend-only` 不启动它。
- AgentScope `/health` 需要认证，脚本只做进程/TCP 就绪探测，不伪造用户或 token；业务服务仍使用公开 `/health`。TCP 可连接不等于完整业务验收。
- 已批准邮箱验证、密码找回与默认关闭的任务邮件通知，契约见 [0081](docs/decisions/0081-email-auth-and-schedule-notifications.md)；实现、模板 UI 预览和 QQ SMTP 联调由主 agent 整合，本页不代表邮件功能测试已通过。
- 旧账号数据仅确认了清理意愿，执行范围尚未确认；不得据此删除数据库、对象存储或 AgentScope 数据。

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
AgentScope 服务、会话绑定、库内文献工具、库外文献发现和引用回查已接入；旧会话执行链已移除，文献解析由独立 worker 消费数据库任务。DeepSeek 浏览器主路径已验证；剩余边界回测见 [TODO.md](TODO.md) 的 R8。

## 数据流向

为了让回答可用，系统会把数据发给外部服务：PDF 发往 MinerU 解析正文；Chunk 文本发往 Embedding 服务生成向量；用户问题与检索到的文献证据发往用户选择的 LLM Provider。邮箱认证会经部署者配置的 SMTP 服务发送验证码和安全邮件；显式开启任务通知后，任务最终回答或失败信息也会经该服务发往用户已验证邮箱（0081）。LLM API Key 由 AgentScope Credential 服务加密保存，不写入日志、对象存储或任务队列。
