# 日志规范

本项目使用 `structlog` 作为应用日志接口，并通过 Python 标准库 `logging` 统一接收 Uvicorn、SQLAlchemy 和第三方库日志。

## 输出

- 所有日志写到 stdout，由容器或部署平台负责收集和轮转。
- 本地默认输出可读文本；生产设置 `LOG_JSON=true`，输出单行 JSON。
- `LOG_LEVEL` 控制最低级别，默认 `INFO`。
- `X-Request-ID` 由中间件读取或生成，并自动加入同一请求内的应用日志。

## 事件命名

事件名采用 `<layer>.<resource>.<action>`：

```text
http.request.completed
api.todo.not_found
service.todo.created
repository.todo.inserted
```

字段名使用 `snake_case`。公共字段包括 `timestamp`、`level`、`logger` 和 `request_id`；请求完成日志还包含 `method`、`path`、`route`、`status_code`、`duration_ms`、`client_ip`。

## 级别

- `DEBUG`：Repository 查询、查询数量和无副作用的业务细节。
- `INFO`：请求成功、业务状态变化和预期结果。
- `WARNING`：4xx 请求和可恢复异常。
- `ERROR`：5xx、数据库失败和需要介入的问题。

## 安全与降噪

- 不记录 Token、Cookie、密码、完整请求体、论文原文或模型提示词。
- 默认不输出 SQL 文本和绑定参数。
- 记录资源 ID、数量、状态、耗时和稳定错误类型。
- 异常堆栈在最接近失败原因的层记录；HTTP 层只记录请求失败结果，避免重复堆栈。
