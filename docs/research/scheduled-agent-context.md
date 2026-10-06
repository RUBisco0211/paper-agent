# 定时 Agent 任务的上下文与运行记录（2026-10-06）

问题：定期任务是否应把前几次运行的完整会话历史带入下一次模型调用？以下只记录厂商官方文档可直接支持的行为。界面把结果放在同一处，与模型每次读到哪些历史，是两个独立问题。

| 产品 | 可核实的运行方式 | 跨次上下文结论 |
|---|---|---|
| ChatGPT Scheduled Tasks | 保存任务指令和日程；关联聊天可管理任务；监控任务可以使用前次运行信息。[官方说明](https://help.openai.com/en/articles/10291617-scheduled-tasks-in-chatgpt) | “可以使用前次信息”只对监控任务有明确表述。文档没有说普通定期任务每次都带入完整聊天历史。 |
| ChatGPT Team Tasks | 每次运行使用任务保存的指令；Previous runs 中每次运行有自己的会话与结果，可在该次会话继续提问。[官方说明](https://help.openai.com/en/articles/20001540-creating-and-managing-team-tasks-in-chatgpt) | 明确区分任务配置、单次运行会话和运行历史；未声明自动继承前次运行的完整会话。 |
| Claude Cowork Scheduled Tasks | 保存 prompt 作为任务指令；**每次运行是独立 Cowork session**，可查看历次结果。[官方说明](https://support.claude.com/en/articles/13854387-schedule-recurring-tasks-in-claude-cowork) | 独立 session 并不等于完全失忆：Cowork 项目有项目级 memory，可从同一项目的既有任务提取并应用信息。[项目记忆说明](https://support.claude.com/en/articles/14116274-organize-your-tasks-with-projects-in-claude-cowork)；但不是逐条拼接全部历史的承诺。 |
| Gemini Scheduled Actions | 保存 prompt 和计划，完成后在任务关联聊天中标为未读；可在该聊天修改未来运行指令。[官方说明](https://support.google.com/gemini/answer/16316416?hl=en) | 文档说明结果的聊天入口和指令更新，没有说明下一次模型调用是否带入历次聊天内容。 |
| Zapier Agents | 定时触发器按间隔启动 Agent；Activity 展示各次运行记录。[官方说明](https://help.zapier.com/hc/en-us/articles/45394909914381-Set-up-your-agent-s-trigger) | 官方触发器文档没有说明自动继承运行历史；不能从“有运行记录”推断“运行记录进入模型上下文”。 |

## 当前 AgentScope 2.0.6 的实现

本项目已安装版本的 `ScheduleData.stateful` 默认是 `false`。调度器在 `false` 时每次创建新 session，在 `true` 时复用同一个固定 session；两种模式都把保存的任务 `description` 作为本次触发提示送入 Agent。因此 AgentScope 原生的“同一执行会话”与“沿用上下文”是绑定的，不能只靠 `stateful=true` 实现同一处展示、每次独立推理。依据：本地已安装源码 `backend/.venv/lib/python3.13/site-packages/agentscope/app/storage/_model/_schedule.py` 与 `backend/.venv/lib/python3.13/site-packages/agentscope/app/_manager/_scheduler/_scheduler_manager.py`。

## 对 Paper Agent 的设计启示（推论，尚非项目决策）

- 用户倾向的“同一会话看历次结果”可以作为**展示与审计容器**；底层仍为每次运行保留独立的 run ID、时间、状态和本次输入/输出。Claude 与 ChatGPT Team 的官方产品都显式展示各次运行。
- 默认每次以保存的用户 prompt、当前项目范围及当前可检索文献启动；**不自动拼接该会话的全部往期消息**。这避免周期越长上下文越膨胀，也避免旧结论覆盖新证据。此条是方案建议，不是对任何厂商内部实现的断言。
- 如果任务需要“追踪变化”“别重复报告”，可明确给它一份受限的前次运行摘要或状态，再让 Agent 比对当前文献；ChatGPT 的监控任务使用前次运行信息、Claude 的项目级 memory 均说明有选择地携带状态是可行的产品形态。摘要的生成、边界与保留策略仍需单独设计。

## 证据边界

上述官方页面主要是用户文档，未公开模型上下文组装的完整规则。尤其不能凭“结果出现在同一聊天”推断完整历史自动进入下一次推理，也不能凭“独立 session”推断项目级记忆不可用。产品行为可能随版本变化，应在实现前复核。
