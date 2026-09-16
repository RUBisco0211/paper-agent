# FastAPI 前后端 SSE 传输选型

> 调研日期：2026-08-23。适用于本仓库 FastAPI 0.141.1。

## 结论

- 后端优先使用 FastAPI 内置的 `fastapi.sse.EventSourceResponse` 和 `ServerSentEvent`，无需默认安装 `sse-starlette`。FastAPI 从 0.135.0 开始提供一等 SSE 支持，当前版本能够编码 `data/event/id/retry/comment`、空闲时发送 keep-alive，并设置 `Cache-Control: no-cache` 与 `X-Accel-Buffering: no`。[FastAPI SSE 教程](https://fastapi.tiangolo.com/tutorial/server-sent-events/) [FastAPI 0.135.0 发布说明](https://github.com/fastapi/fastapi/releases/tag/0.135.0)
- Agent/聊天请求推荐 `POST /runs/stream`，前端用 `fetch` 读取 `ReadableStream`，并用 `eventsource-parser` 解析 SSE。原生 `EventSource` 构造器只接受 URL 和 `withCredentials`，不支持 POST body 或任意 Authorization header。[MDN EventSource 构造器](https://developer.mozilla.org/en-US/docs/Web/API/EventSource/EventSource) [Fetch 流式响应](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch#streaming_the_response_body) [eventsource-parser](https://github.com/rexxars/eventsource-parser)
- 如果任务需要断线后可靠续传，则改成“两步式”：`POST /runs` 创建任务，随后用原生 `EventSource` 连接 `GET /runs/{id}/events`。每个事件持久化递增 `id`，服务端根据 `Last-Event-ID` 补发。这是协议原生的恢复机制。[WHATWG SSE](https://html.spec.whatwg.org/dev/server-sent-events.html)

## 推荐事件模型

不要把所有内容都塞进匿名 `message`。建议固定事件类型：

| event | data 用途 |
|---|---|
| `run.started` | run ID、模型等元数据 |
| `message.delta` | 增量文本 |
| `tool.started` / `tool.completed` | 工具执行状态 |
| `run.completed` | 最终状态、usage |
| `run.failed` | 稳定错误码和可展示信息 |

每条 `data` 使用 JSON。传输开始后 HTTP 状态已经发送，后续业务错误应作为 `run.failed` 事件发送，而不是期望改成 HTTP 4xx/5xx。鉴权和参数检查必须放在普通依赖中，在流创建前完成。

## 后端用法

```python
from collections.abc import AsyncIterable

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse, ServerSentEvent

router = APIRouter()


@router.post("/runs/stream", response_class=EventSourceResponse)
async def stream_run(_: None = Depends(check_access)) -> AsyncIterable[ServerSentEvent]:
    yield ServerSentEvent(event="run.started", data={"run_id": "run_123"})
    async for chunk in service.stream():
        yield ServerSentEvent(event="message.delta", data={"text": chunk})
    yield ServerSentEvent(event="run.completed", data={"run_id": "run_123"})
```

应使用装饰器上的 `response_class=EventSourceResponse` 并让路径函数本身 `yield`，这样才能进入 FastAPI 的内置 SSE 编码和 keep-alive 路径。[FastAPI SSE API](https://fastapi.tiangolo.com/reference/sse/)

生成器应在 `finally` 中释放上游模型流、数据库资源和其他连接。浏览器取消 `fetch` 时使用 `AbortController`；ASGI 取消会沿生成器传播，代码不要吞掉 `CancelledError`。

## 前端选择

### 简单 GET 订阅

使用浏览器原生 `EventSource`。它自动重连，并在收到 `id` 后通过 `Last-Event-ID` 恢复；适合通知流、任务状态订阅。SSE 是服务端到客户端的单向连接。[MDN SSE 指南](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)

### POST + JSON + Bearer Token

使用原生 `fetch` + `eventsource-parser`：

```ts
import { EventSourceParserStream } from "eventsource-parser/stream"

const response = await fetch("/api/runs/stream", {
  method: "POST",
  headers: {
    Accept: "text/event-stream",
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  },
  body: JSON.stringify(input),
  signal: controller.signal,
})

const events = response.body!
  .pipeThrough(new TextDecoderStream())
  .pipeThrough(new EventSourceParserStream())

for await (const event of events) {
  // JSON.parse(event.data)
}
```

`eventsource-parser` 当前提供 `TransformStream`、事件 ID、retry 和最大缓冲区限制，且不绑定传输实现。[eventsource-parser 文档](https://www.npmjs.com/package/eventsource-parser)

## 部署与扩展

- FastAPI 当前会设置 `X-Accel-Buffering: no`；如果代理配置忽略该头，还需为 SSE 路由显式设置 Nginx `proxy_buffering off`。Nginx 默认开启代理响应缓冲。[Nginx proxy buffering](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_buffering)
- 确保负载均衡器 idle timeout 大于心跳间隔。FastAPI 内置 SSE 当前空闲约 15 秒发送注释心跳。
- 不要对 SSE 响应启用 GZip；压缩和额外缓冲会破坏低延迟逐事件交付。
- HTTP/1.x 下浏览器对同域 SSE 连接数通常很低（MDN 提示约 6 个）；生产入口应启用 HTTP/2，并尽量让一个页面只维护一条流。[MDN SSE 连接限制](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- 单进程、连接绑定的生成任务可先放内存。上多 worker/多实例或要求断线续传时，事件不能只存在某个进程内；应持久化 run/event，或通过 Redis Streams、PostgreSQL、消息代理做跨实例传递。

## 何时使用 `sse-starlette`

只有确实需要 FastAPI 内置实现没有暴露的响应级配置，例如自定义 ping 间隔、`send_timeout`、直接构造并返回响应、专门的 client-close callback 时再引入。它提供这些能力，但会增加一个额外依赖。[sse-starlette 官方仓库](https://github.com/sysid/sse-starlette)
