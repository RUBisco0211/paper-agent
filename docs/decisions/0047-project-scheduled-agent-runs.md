# 0047 项目定时任务沿用 AgentScope 调度，历次运行独立

- DATE: 2026-10-06
- TAGS: product, agent, data, frontend
- STATUS: 已被 0049 取代
- SUPERSEDES: 0017 中待定的结果投递形态；细化 0046

## DECISION

用户为所属项目保存自定义 prompt 与执行时间。AgentScope 持有 schedule、触发和每次运行的 session/messages，`stateful=false`，每次运行不默认带入此前完整会话历史。业务库只保存 `schedule_id → user_id/project_id`，并为每次定时 session 建立带 `schedule_id` 的项目范围绑定；绑定失败不得开放文献工具。日历按项目展示任务，在同一任务页面汇集历次运行；普通对话列表不展示定时 session。项目仍有任务时拒绝删除，先删除任务及其运行记录。

## REJECTED

- `stateful=true` 复用一个 AgentScope session：会把历次运行上下文累积进模型调用。
- 为此另建调度 worker：AgentScope 已提供持久任务、cron 触发和按任务列出运行 session。
- 把任务结果放进普通会话列表，或把回答正文复制到业务库。

## RATIONALE

任务页面的连续记录是展示需求，独立运行是上下文需求。两者可由 `schedule_id` 聚合多个运行 session 实现；业务库只记录项目授权关系，避免依赖 AgentScope 表结构。

## OUT OF SCOPE

跨次摘要记忆、Agent 写工具、通知投递。

## OPEN

定时失败后的自动重试与费用上限另定。
