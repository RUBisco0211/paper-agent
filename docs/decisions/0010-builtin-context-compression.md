# 0010 上下文压缩用框架的 ContextConfig

- DATE: 2026-10-05
- TAGS: agent
- STATUS: 当前
- SUPERSEDES: —

## DECISION

上下文压缩用 `agentscope.agent.ContextConfig`（`trigger_ratio` ≤0.9、`reserve_ratio`、`tool_result_limit`、`compression_prompt`、`summary_schema`），自动触发，不自己实现。摘要为结构化五字段：`task_overview` / `current_state` / `important_discoveries` / `next_steps` / `context_to_preserve`。

## REJECTED

- 自己做截断或摘要压缩：框架已有且更完整（工具调用与结果对不会被拆散）。
- MVP 完全不管压缩：长会话必然撞上下文窗口，属已知失败模式。
- 压缩事件写入历史表：压缩发生在 agent 进程内，不写 `messages` 表，历史展示不受影响，无需记录。

## RATIONALE

`_service/_chat.py` 中没有任何压缩相关代码 —— 压缩是 agent 进程内的上下文管理，与持久化历史解耦。这正是 0009 敢砍掉 Entry 表的前提。

## OUT OF SCOPE

`offloader`（被截断内容落盘、按需读回），MVP 不开；手动 `compress_context()` 触发的入口。

## OPEN

`trigger_ratio` 取值与模型上下文长度的来源；压缩时那次额外 LLM 调用的费用归属与展示。
