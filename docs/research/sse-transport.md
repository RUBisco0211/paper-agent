# 前后端 SSE 传输

- DATE: 2026-08-23（本次改写仅压缩结构，未更新结论）
- STATUS: **已失效** —— 传输层已由 agentscope 的 `GET /sessions/{id}/stream` 接管（见决策 0006 / 0009）。保留仅作历史依据，不要据此实现。

## 结论

- 后端用 FastAPI 内置 `fastapi.sse.EventSourceResponse` + `ServerSentEvent`，不默认装 `sse-starlette`。FastAPI 从 0.135.0 起提供一等 SSE 支持，编码 `data/event/id/retry/comment`，空闲发 keep-alive，并设 `Cache-Control: no-cache` 与 `X-Accel-Buffering: no`。
- Agent 请求用 `POST /runs/stream` + `fetch` 读 `ReadableStream` + `eventsource-parser` 解析。原生 `EventSource` 不支持 POST body 或自定义 Authorization header。
- 需要断线续传时改两步式：`POST /runs` 建任务，再用原生 `EventSource` 连 `GET /runs/{id}/events`，事件持久化递增 `id`，服务端按 `Last-Event-ID` 补发。
- 固定事件类型，不要全塞进匿名 `message`：`run.started` / `message.delta` / `tool.started` / `tool.completed` / `run.completed` / `run.failed`。
- 流开始后 HTTP 状态已发出，后续业务错误必须作为 `run.failed` 事件发，不能指望改成 4xx/5xx。鉴权与参数检查放在普通依赖里，在流创建前完成。

## 依据

- 生成器应在 `finally` 里释放上游模型流与数据库资源；浏览器取消用 `AbortController`，ASGI 取消会沿生成器传播，不要吞 `CancelledError`。
- 部署：代理要尊重 `X-Accel-Buffering: no`（Nginx 显式 `proxy_buffering off`）；LB idle timeout 要大于心跳间隔（FastAPI 内置约 15 秒）；SSE 响应不要开 GZip；HTTP/1.x 下同域连接数约 6 条，生产入口开 HTTP/2，一个页面尽量只维护一条流。
- 单进程可把连接绑定的任务放内存；上多 worker 或要求续传时，事件不能只存在某个进程内，要持久化或走 Redis Streams / PostgreSQL / 消息代理。

## 备选方案与取舍

| 方案 | 结论 | 理由 |
|---|---|---|
| `sse-starlette` | 默认不装 | 只在需要自定义 ping 间隔、`send_timeout`、直接构造响应或 client-close callback 时才引入 |
| 原生 `EventSource` 直连业务流 | 否 | 只接受 URL 与 `withCredentials`，带不了 POST body 和 Bearer token |
| WebSocket 双向 | 否 | 本项目只有服务端到客户端的单向事件流 |

## 参考

- [FastAPI SSE 教程](https://fastapi.tiangolo.com/tutorial/server-sent-events/) · [FastAPI SSE API](https://fastapi.tiangolo.com/reference/sse/) · [0.135.0 发布说明](https://github.com/fastapi/fastapi/releases/tag/0.135.0)
- [WHATWG SSE](https://html.spec.whatwg.org/dev/server-sent-events.html) · [MDN EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource/EventSource)
- [eventsource-parser](https://github.com/rexxars/eventsource-parser) · [Nginx proxy_buffering](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_buffering)
