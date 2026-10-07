# 0044 R7 解析任务恢复与项目删除顺序

- DATE: 2026-10-06
- TAGS: ingest, product, agent
- STATUS: 解析 worker 部分已被 0056 取代；项目删除部分仍当前
- SUPERSEDES: —

## DECISION

业务 API 只把摄取 job 写入数据库；独立单 worker 按创建时间领取 queued job，启动时把遗留 running job 与 running stage 退回待执行。项目删除前先通过 AgentScope 删除项目会话，再删除业务绑定与引用；若仍有绑定，业务 API 返回冲突，不级联删除。

## REJECTED

- API 进程继续执行 MinerU：同步解析会占用服务资源，且无法隔离故障。
- 删除项目时直接级联业务绑定：会留下 AgentScope 中不可见的孤立会话。
- 只在内存里标记任务：进程退出后无法恢复。

## RATIONALE

单 worker 启动恢复与数据库领取满足当前单机部署；删除顺序保证跨数据库的失败可重试。

## OUT OF SCOPE

多 worker 租约、旧会话历史迁移、真实 Provider 浏览器验收。

## OPEN

未来启用多个 worker 时需另定 lease 与超时恢复规则。
