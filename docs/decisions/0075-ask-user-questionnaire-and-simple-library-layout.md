# 0075 Agent 提问问卷

- DATE: 2026-10-09
- TAGS: agent, frontend, product
- STATUS: 当前
- SUPERSEDES: —；文献页侧栏修正已合并进 0045

## DECISION

交互会话的 Agent 可调用 `ask_user`，一次提出最多三道单选、多选或自由输入问题。该工具使用 AgentScope 的外部执行机制暂停当前回复；前端使用现有 `@shadcn/react` Questionnaire 呈现，用户提交答案后以 `ExternalExecutionResultEvent` 返回对应的 tool call，同一回复继续。答案只进入该会话的工具结果，不另建问卷表；重复提交和无效问题需在前端阻止。

## REJECTED

- 使用普通权限确认卡片收集答案：该事件只返回确认布尔值，无法携带问卷答案。
- 答案作为新用户消息开启下一轮：无法恢复等待中的工具调用，丢失同一轮上下文。

## RATIONALE

外部执行事件已覆盖暂停、重连与恢复状态；复用它可以避免另建一套问答状态机。问卷原语已在前端依赖中，无需新增组件库。

## OUT OF SCOPE

问卷历史管理、问卷答案跨会话复用、工具权限审批。

## OPEN

无。
