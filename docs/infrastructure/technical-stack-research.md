# FastAPI 单体后端技术选型研究

> 调研日期：2026-08-23。范围基于本仓库当前的 Python `>=3.13`、FastAPI `>=0.141.1`（锁文件当前解析为 FastAPI 0.141.1、Starlette 1.6.0）。外部事实只引用项目官方文档、官方仓库或 Python 官方文档。

## 结论先行

建议采用下面这套“够用且可演进”的基线：

- 数据库：**SQLAlchemy 2.0 typed declarative + Alembic**；保留现有独立 Pydantic schema。数据库确定为 PostgreSQL 后再选择驱动。当前路由仍是同步 `def`，没有并发数据库 I/O 的证据时先用同步 `Session` 最简单；如果随后接口链路会整体异步化（例如并发调用模型/API）并确定使用异步驱动，再统一切到 `AsyncSession`，不要在同一业务链路混搭同步与异步 session。
- 日志：**structlog + Python 标准库 `logging`**。structlog 负责结构化字段、JSON/开发态可读输出和 `contextvars`；stdlib 作为统一底座接住 Uvicorn、SQLAlchemy 和第三方库日志。不建议本项目再引入 Loguru 作为第二套日志体系。
- 请求标识：需要按请求串联日志时使用 **asgi-correlation-id**，默认 `X-Request-ID` 即可，并把它加入日志字段；有跨域前端时记得在 CORS 中暴露该响应头。
- 中间件：只默认考虑请求 ID/访问日志；**CORS、TrustedHost、请求体限制**按部署条件开启。GZip、HTTPSRedirect 通常优先交给反向代理；应用内限流不是当前默认项。
- 限流：**暂不安装 SlowAPI**。其官方文档仍明确标为 alpha，且 WebSocket 不受支持；真正出现公开接口滥用风险时，优先在网关/反向代理统一限流。单实例、小范围接口确需装饰器限流时才评估 SlowAPI，生产多实例必须使用 Redis 等共享后端。

## 1. ORM 与迁移

### SQLAlchemy 2.0 + Alembic

SQLAlchemy 同时提供 Core 和 ORM，并有正式的 asyncio 扩展；当前 2.0 官方文档明确包含 `AsyncEngine`、`AsyncSession` 与异步驱动方言。[SQLAlchemy 2.0 asyncio 官方文档](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)

适合本项目的原因：

- 与现有的 `schemas/`、`repositories/` 分层自然匹配：数据库模型负责持久化映射，Pydantic 模型负责 API 输入输出，不必让一个类承担两种边界职责。
- SQLAlchemy 官方项目元数据列出 Python 3.13 支持；当前 2.0 稳定线可用于本仓库，而不必采用 2.1 beta。[SQLAlchemy 官方 `pyproject.toml`](https://github.com/sqlalchemy/sqlalchemy/blob/main/pyproject.toml)
- 如果采用 asyncio，应通过 `create_async_engine()`/`async_sessionmaker()` 创建每请求 session；官方文档强调一个 `AsyncSession` 不能安全地被多个并发任务共享，`asyncio.gather()` 中每个任务应使用独立 session。[AsyncSession 并发使用说明](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks)
- Alembic 没有独立的 async API，但官方提供 async 初始化模板，并通过 SQLAlchemy async engine 的 `run_sync()` 执行迁移与 autogenerate，因此它与异步业务代码并不冲突。[Alembic asyncio cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic)

异步不是 FastAPI 项目的强制选项。当前示例路由和 service/repository 都是同步调用；直接引入 async ORM 会迫使整条调用链改为 `async def`/`await`。只有确定数据库驱动和高并发 I/O 路径后，这个复杂度才有收益。若未来选择 SQLite 做本地原型，SQLAlchemy 官方也说明 `aiosqlite` 实际通过每连接后台线程包装 `pysqlite`，并不是真正的非阻塞 socket I/O，因此不应把“SQLite async”当作性能理由。[SQLAlchemy SQLite/aiosqlite 方言说明](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#aiosqlite)

### SQLModel

SQLModel 由 FastAPI 作者维护，建立在 SQLAlchemy 与 Pydantic 之上；官方 FastAPI 教程把它作为简短 SQL 教程的默认选择，并展示了同一类作为表模型和数据模型的低样板写法。[FastAPI SQLModel 数据库教程](https://fastapi.tiangolo.com/tutorial/sql-databases/)

它更适合快速 CRUD、原型或希望表模型与校验模型高度复用的项目。对本仓库而言，它的主要优势会被现有独立 `schemas` 和 repository 边界抵消；复杂关系、加载策略、迁移排错最终仍要理解底层 SQLAlchemy。当前官方发布仍使用 `0.0.x` 版本线（调研时最新发布页显示 0.0.38），这不是“不稳定”的直接证明，但意味着采用者应更仔细锁版本并检查变更。[SQLModel 官方 releases](https://github.com/fastapi/sqlmodel/releases)

**选择：SQLAlchemy 2.0 + Alembic，不选 SQLModel。** 这不是因为 SQLModel 不可用，而是当前代码结构已经明确分离 API schema 与数据存储，直接使用底层 ORM 的边界更清楚。

### 建议依赖时机

- 确定数据库后立即加入：`sqlalchemy>=2.0,<2.1`、`alembic`。
- 仅在确定异步链路时使用 `sqlalchemy[asyncio]`，并添加对应驱动；SQLAlchemy 官方把 `greenlet` 纳入该 extra。[SQLAlchemy 安装与 asyncio 依赖说明](https://docs.sqlalchemy.org/en/20/intro.html#asyncio-support)
- PostgreSQL 驱动在 `psycopg`（支持 sync/async）与 `asyncpg` 之间按团队偏好决定；数据库尚未确定时不要提前安装驱动。
- 生产环境用 Alembic 迁移，不在应用启动时无条件 `metadata.create_all()`。

## 2. 结构化日志

### Python `logging`

标准库 logging 有 logger、handler、filter、formatter 的成熟生态，第三方库通常也以它作为公共接口；配置可统一接管 Uvicorn 和 SQLAlchemy 日志。[Python 3.13 logging 官方文档](https://docs.python.org/3.13/library/logging.html)

它的不足是结构化事件需要自己约定 `extra`、JSON formatter 和上下文字段。小项目只需文本日志时，stdlib 已经足够；本项目若要检索 agent/job/request 等字段，单独手写这些胶水会逐渐变多。

### structlog

structlog 的处理链以字典事件为中心，可输出 JSON、logfmt 或开发态控制台格式，并能转发到标准库 logging；官方也提供 stdlib 集成配置。[structlog 官方文档](https://www.structlog.org/en/stable/) [structlog 标准库集成](https://www.structlog.org/en/stable/standard-library.html)

其 `contextvars` 支持线程与 async 上下文，可把 request ID 等字段绑定到当前执行上下文；官方同时提醒 Starlette/FastAPI 这种 sync/async 混合应用中，两类执行上下文可能彼此隔离，因此日志上下文应在统一的 ASGI 边界设置和清理。[structlog contextvars 官方文档](https://www.structlog.org/en/stable/contextvars.html)

**选择：structlog 作为应用日志 API，底层仍走 stdlib logging。** 生产输出单行 JSON 到 stdout，开发环境输出可读 console；不要让业务代码直接依赖 Uvicorn 的 logging 配置。

### Loguru

Loguru 的优势是开箱即用、单例 logger、文件轮转/保留/压缩方便，`serialize=True` 可输出 JSON，`enqueue=True` 可通过队列降低日志调用阻塞并支持多进程写入。[Loguru 官方 overview](https://loguru.readthedocs.io/en/stable/overview.html) [Loguru logger API](https://loguru.readthedocs.io/en/stable/api/logger.html)

但它采用独立的全局 logger 模型；为了统一 Uvicorn、SQLAlchemy 和其他使用 stdlib logging 的依赖，仍需拦截或桥接标准库日志。其 `diagnose` 还可能显示局部变量值，官方明确要求生产环境设为 `False` 以避免泄露敏感信息。[Loguru `add()` 参数说明](https://loguru.readthedocs.io/en/stable/api/logger.html#loguru._logger.Logger.add)

**本项目不选 Loguru。** 它很适合脚本和偏文件日志的应用，但这里 structlog + stdlib 对结构化字段和第三方日志统一更直接。

## 3. 中间件

Starlette 已内建 `ServerErrorMiddleware` 和 `ExceptionMiddleware`，并提供 CORS、Session、HTTPSRedirect、TrustedHost、RequestBodyLimit 与 GZip 等中间件；不应为已有能力重复引第三方包。[Starlette middleware 官方文档](https://www.starlette.io/middleware/)

建议按需启用：

| 中间件 | 建议 | 触发条件 |
|---|---|---|
| `CorrelationIdMiddleware` | 推荐在接入结构化日志时启用 | 需要跨 API/service/repository 串联同一次请求日志 |
| `CORSMiddleware` | 有独立浏览器前端才启用 | 明确列出 origin；凭证模式不能用通配 origin/method/header |
| `TrustedHostMiddleware` | 生产直连 ASGI 或希望应用做纵深防御时启用 | 配置真实域名；它用于防御 Host header 攻击 |
| `RequestBodyLimitMiddleware` | 有上传、解析或公网接口时启用 | 限制异常大请求体；额度按接口需求设置 |
| `GZipMiddleware` | 先由网关/CDN 处理，测量后再在应用开启 | 大量可压缩响应且上游未压缩；压缩会消耗 CPU |
| `HTTPSRedirectMiddleware` | 通常交给反向代理/负载均衡器 | 应用直接终止 TLS 且代理头配置明确时才考虑 |
| `SessionMiddleware` | 默认不启用 | 只有 cookie session 登录需求时需要；纯 Bearer API 不需要 |

FastAPI 官方说明，使用 `add_middleware()` 时最后添加者位于最外层，请求按外到内、响应反向执行，因此 request ID、异常、CORS 等行为必须结合顺序测试。[FastAPI 中间件执行顺序](https://fastapi.tiangolo.com/tutorial/middleware/#multiple-middleware-execution-order)

自定义横切逻辑优先写纯 ASGI middleware。Starlette 官方记录了 `BaseHTTPMiddleware` 会妨碍 `ContextVar` 向上传播，并建议用 pure ASGI middleware 避免这一限制；这对 request ID 和 structlog 上下文尤其重要。[Starlette BaseHTTPMiddleware 限制](https://www.starlette.io/middleware/#limitations)

### asgi-correlation-id

该中间件会读取或生成请求 ID，默认使用 `X-Request-ID`，把 ID 保存在上下文中并支持标准 logging filter 与 structlog 集成；官方仓库的当前发布说明也列出了 Python 3.13 支持。[asgi-correlation-id 官方仓库](https://github.com/snok/asgi-correlation-id) [官方 releases](https://github.com/snok/asgi-correlation-id/releases)

注意官方 README 说明：默认情况下，未处理的 500 响应可能没有 `X-Request-ID` 响应头，需要自定义异常处理；若有 CORS 前端，还需在 `expose_headers` 中暴露该 header。这两点都应加入测试。[asgi-correlation-id 异常与 CORS 说明](https://github.com/snok/asgi-correlation-id#exception-handling)

### SlowAPI

SlowAPI 支持 endpoint 装饰器、全局/共享限制，以及 Redis、Memcached、内存后端；但官方文档明确称其为 alpha，并列出必须显式保留 `request` 参数、WebSocket 未支持等限制。[SlowAPI 官方文档](https://slowapi.readthedocs.io/en/stable/)

因此它不应成为基础模板的默认中间件。公开生产 API 的限流通常更适合放在 Cloudflare、API Gateway、Nginx/Envoy 等入口层，能在请求进入 Python 进程前拒绝流量。若单体内部确需按用户/路由限流，可再引入 SlowAPI，并使用 Redis 共享计数，不能在多 worker/多实例场景依赖内存后端。

## 4. 分阶段落地

1. **现在**：配置 structlog + stdlib logging；接入 asgi-correlation-id；为每条访问/异常日志统一 `request_id`、method、path、status_code、duration_ms 字段。
2. **数据库确定时**：加入 SQLAlchemy 2.0 与 Alembic；先决定同步还是异步，再选驱动并一次性贯通 route → service → repository。不要让 repository 返回 API schema，改为返回 ORM/domain 对象或明确 DTO。
3. **部署信息确定时**：按前端 origin、真实 host、反向代理职责配置 CORS、TrustedHost、请求体限制；保留健康检查不做冗余日志。
4. **出现实际风险或指标时**：再增加 GZip、应用内限流、OpenTelemetry/Sentry、Prometheus 等。不要预装一组尚无使用方的中间件。

## 推荐包清单

当前就值得加入：

```text
structlog
asgi-correlation-id
```

数据库确定后加入：

```text
sqlalchemy>=2.0,<2.1
alembic
# 异步方案改为 sqlalchemy[asyncio]，另加实际数据库驱动
```

暂不加入：

```text
sqlmodel
loguru
slowapi
```
