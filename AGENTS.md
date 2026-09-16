# Paper Agent — 协作约定

改动本仓库前先读这些文档（按需要）：

| 文档 | 什么时候必读 |
|---|---|
| [docs/frontend/ui-spec.md](docs/frontend/ui-spec.md) | **改任何前端代码/文案前必读**：文案只写用户需要知道的事，布局与 shadcn 组件规范 |
| [docs/overview/minimal-mvp.md](docs/overview/minimal-mvp.md) | 涉及功能范围、接口契约、验收标准时（功能范围以此为准） |
| [docs/overview/prototype.md](docs/overview/prototype.md) | 涉及领域模型、数据模型、架构分层时 |
| [docs/overview/implementation-status.md](docs/overview/implementation-status.md) | 确认“已经做了什么/明确没做什么”，避免把桩当成已完成 |
| [CONTEXT.md](CONTEXT.md) | 命名与领域术语（Paper / User Paper / Project / Session / Entry …） |
| [docs/infrastructure/logging-conventions.md](docs/infrastructure/logging-conventions.md) | 改后端日志或错误码时 |

约定：

- 代码注释、日志事件名、错误码用英文；面向用户的文案与文档用中文。
- 后端提交遵循 conventional commits，每个接口/功能一次提交；前端同理。
- 后端测试依赖真实 PostgreSQL（`docker compose up -d postgres`）：`cd backend && uv run pytest -q`。
- 前端改动必须通过 `pnpm run typecheck && pnpm run test && pnpm run build`。
- 本地联调用 `./start.sh`（启动数据库 + 后端 + 前端，Ctrl-C 全部停止）。
