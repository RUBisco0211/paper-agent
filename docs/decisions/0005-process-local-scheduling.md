# 0005 后台任务与实时事件留在 FastAPI 进程内

- DATE: 2026-09-24
- TAGS: arch, infra
- STATUS: 已被 0006 与 0012 取代（实时事件交给框架；解析移到独立 worker 进程）
- SUPERSEDES: 旧原型 §12 的「Celery workers + Redis + MinIO 三层」目标架构

## DECISION

解析、分块、向量索引等后台处理与 Agent 生成都留在 FastAPI 进程内：任务用 `backend/app/platform/tasks.py` 的 `AsyncioTaskScheduler`，实时事件用 `conversation/events.py` 的进程内 `EventBroker`。不引入 Celery、Redis、多进程协调。

## REJECTED

- Celery workers 处理后台流水线：需要额外 broker、worker 进程与序列化边界，单机单进程场景没有收益。
- Redis 作为热 Entry 日志与 SSE 断线重放层（旧原型 §9.4 / §11.2）：引入有状态中间件只为换一个热日志位置，且要承担 AOF 持久语义。
- 多实例水平扩展与跨实例事件传递：当前并发 <10，进程内状态足够。
- 进程重启后自动恢复未完成任务：接受重启丢失，不为此引入任务持久化与恢复机制。

## RATIONALE

部署形态是单机 Docker Compose。跨进程、跨实例的恢复与协调机制，成本远高于当前规模能获得的收益。可观测性与幂等重试放在任务内部实现，比放在中间件上更直接。

## OUT OF SCOPE

多 worker、多实例、Redis Streams / 消息代理做跨实例事件传递、任务断点续跑。

## OPEN

进程重启时未完成任务的状态如何标记（当前未见明确处理）。
