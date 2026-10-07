# 0050 定时运行会话可继续对话

- DATE: 2026-10-07
- TAGS: product, frontend, agent
- STATUS: 当前
- SUPERSEDES: —

## DECISION

定时任务详情保留运行预览，并提供“打开会话”入口。运行会话在 `/scheduled/:scheduleId/runs/:sessionId` 的主区域显示，保留定时任务侧栏；用户可以在该 run 的 session 内继续对话。打开前校验 session 属于当前用户可见的任务及其运行记录。运行会话继续只出现在定时任务页，不进入普通对话列表。非 stateful 任务的下次执行仍创建独立 session，不继承用户在旧 run 中的追加对话。消息表格保持单层边框和横向滚动。

## REJECTED

- 把运行会话加入普通对话列表：任务与普通会话混杂。
- 把继续对话写入任务 prompt 或下次运行：会意外改变后续自动执行的输入。

## RATIONALE

运行结果需要可追问，同时维持每次运行与任务管理入口的关系。

## OUT OF SCOPE

跨运行上下文合并、任务 prompt 编辑、stateful 任务语义变更。

## OPEN

无。
