# 0012 解析跑在独立 worker 进程，DB 当队列

- DATE: 2026-10-05
- TAGS: ingest, infra
- STATUS: 当前
- SUPERSEDES: 0005 中「解析留在 FastAPI 进程内」那部分

## DECISION

MinerU 解析跑在独立 worker 进程：只消费数据库里的 job 队列、写对象存储、更新 job / stage / chunk 表。业务 API 进程不解析。摄取编排（四阶段 + 阶段级重试）与状态机仍在业务服务。共享同一个 PostgreSQL，DB 即队列与协调者。

## REJECTED

- 留在业务服务进程内：MinerU 是同步库，会阻塞事件循环拖慢会话响应；OOM 会带走整个服务。
- 做成独立 HTTP 服务：多一套 API 契约、鉴权与部署，当前没有独立扩缩容需求。
- 引入 Celery + broker：单机场景无收益（0005 已否决），且 DB 已经能当队列。

## RATIONALE

要的是资源隔离与故障隔离，不是服务边界。worker 不对外提供 API，所以跨服务事务一致性这个麻烦根本不存在。

## OUT OF SCOPE

GPU 机器独立部署、多 worker 抢占任务的 lease 租约（单 worker 不需要）、跨机调度。

## OPEN

worker 崩溃后 job 的状态标记与自动回收；将来多 worker 时是否采用框架文档的 lease 机制。
