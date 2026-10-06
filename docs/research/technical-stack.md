# 后端技术选型

- DATE: 2026-08-23（本次改写仅压缩结构，未更新结论）
- STATUS: 当前

## 结论

- **ORM**：SQLAlchemy 2.0 typed declarative + Alembic，保留独立 Pydantic schema。生产用 Alembic 迁移，不在启动时 `create_all()`。
- **同步/异步**：当前路由是同步 `def`，先用同步 `Session`。要切 `AsyncSession` 就整条链路一起切，不在同一业务链路混搭。
- **日志**：structlog 作为应用日志 API，stdlib `logging` 作统一底座接住 Uvicorn / SQLAlchemy 第三方日志。生产单行 JSON 到 stdout。
- **请求标识**：asgi-correlation-id，默认 `X-Request-ID`，进日志字段；有跨域前端时在 CORS `expose_headers` 暴露。
- **中间件**：只默认加请求 ID / 访问日志。CORS、TrustedHost、请求体限制按部署条件开；GZip、HTTPSRedirect 交给反向代理。
- **限流**：不装 SlowAPI。真出现滥用风险时在网关层做；应用内限流必须配 Redis 共享计数。

## 依据

- SQLAlchemy 2.0 与当前 `schemas/` + repo 分层天然匹配：表模型负责持久化，Pydantic 负责 API 输入输出，一个类不承担两种边界。
- structlog 的 `contextvars` 可绑定 request ID；Starlette 这种 sync/async 混合应用里两类执行上下文可能隔离，日志上下文要在统一 ASGI 边界设置与清理。
- 自定义横切逻辑写纯 ASGI middleware：`BaseHTTPMiddleware` 会妨碍 `ContextVar` 向上传播，对 request ID 与 structlog 上下文致命。
- FastAPI 用 `add_middleware()` 时最后添加者位于最外层，request ID / 异常 / CORS 的顺序必须结合测试确认。

## 备选方案与取舍

| 方案 | 结论 | 理由 |
|---|---|---|
| SQLModel | 不选 | 低样板优势被现有独立 schema 与 repo 边界抵消；复杂关系与迁移排错仍要回到 SQLAlchemy，且仍处 `0.0.x` 版本线 |
| Loguru | 不选 | 独立全局 logger 模型，统一第三方 stdlib 日志仍需桥接；`diagnose` 可能泄漏局部变量，生产必须关 |
| SlowAPI | 暂不装 | 官方标 alpha，WebSocket 不支持；多实例必须 Redis 后端 |
| `aiosqlite` 当性能理由 | 不成立 | 实际是每连接后台线程包装 `pysqlite`，不是非阻塞 socket I/O |

驱动在 `psycopg` 与 `asyncpg` 之间按偏好选；数据库未定时不提前装驱动。

## 参考

- [SQLAlchemy asyncio](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) · [Alembic asyncio cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic)
- [structlog contextvars](https://www.structlog.org/en/stable/contextvars.html) · [Python logging](https://docs.python.org/3.13/library/logging.html)
- [Starlette middleware 限制](https://www.starlette.io/middleware/#limitations) · [FastAPI 中间件顺序](https://fastapi.tiangolo.com/tutorial/middleware/#multiple-middleware-execution-order)
- [asgi-correlation-id](https://github.com/snok/asgi-correlation-id#exception-handling) · [SlowAPI](https://slowapi.readthedocs.io/en/stable/)
