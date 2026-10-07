# 0051 运行记录直接打开会话

- DATE: 2026-10-07
- TAGS: product, frontend
- STATUS: 当前
- SUPERSEDES: 0050 的抽屉运行预览与隐藏入口

## DECISION

定时任务抽屉保留任务信息与运行记录；点击任一运行记录，直接在 `/scheduled/:scheduleId/runs/:sessionId` 主区域打开完整会话，定时任务侧栏保持可见，并可返回月视图。会话继续支持提问，且不进入普通对话列表。运行记录的时间按任务时区展示；AgentScope 未带时区后缀的 session 时间按 UTC 解析。

## REJECTED

- 点击记录只在抽屉切换预览、再点标题栏图标打开会话：入口隐蔽且多一次操作。
- 按浏览器本地时区解析 AgentScope 的无后缀 UTC 时间：运行时间显示错误。

## RATIONALE

每条运行记录就是对应会话的入口；时间应与任务设置的时区一致。

## OUT OF SCOPE

改变调度触发时间、合并不同运行会话。

## OPEN

无。
