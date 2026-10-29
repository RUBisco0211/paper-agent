# 0098 AgentScope 升级到 2.0.11

- DATE: 2026-10-29
- TAGS: agent, arch, data
- STATUS: 当前
- SUPERSEDES: —

## DECISION

- `agentscope[service,storage-sql]` 由 2.0.6 升到 2.0.11；同时带入 `mcp` 1.29→2.3、新依赖 `httpx2`。
- 适配四处破坏性变更：`upsert_session` 在 `source` 前插入 `origin` 且调度器改传 `ScheduleOrigin`；`assign_workspace_id` 变异步；`list_skills` / `list_mcps` 新增 `agent_id`/`session_id` 关键字参数；结构化输出需要 `usage`。
- 会话来源判定同时接受 `origin` 与旧 `source`；`source` 系列字段仍可读但已 deprecated，本版不迁移调用方。
- `paper_agent_as` 由 2.0.11 自带 alembic 迁移到 `0004_sops`；升级前必须 `pg_dump` 备份。
- 存量 agent 记录的 `context_config`/`react_config`/`invite_config` 迁进 `chat_config`，否则新的 `AgentData` 会用默认值覆盖自定义压缩提示词。
- 升级后 `ChatService` 的 run 循环依赖 `InboxMiddleware` 清空 inbox；替换 `reply_stream` 的测试必须自己 drain，否则同一 wakeup 会被反复取出导致死循环。

## REJECTED

- 只改版本号不备份 AS 库：迁移随启动执行且不可回退。
- 保留按位置传参调用 `upsert_session`：2.0.11 形参顺序变化会把 `source` 送进 `origin`，会话创建直接崩溃。
- 用 `record.source` 判断是否为定时会话：2.0.11 的调度器不再传 `source`，会漏判并把定时运行当成普通会话。
- 为消 deprecation 警告同时改写全部调用方为 `origin.type`：与升级无关，留给后续独立任务。

## RATIONALE

2.0.11 提供更新的模型目录（gpt-6.x、claude-5.5、qwen3.8、grok-4.6/4.7、gemini-3.7/3.8），且 2.0.6 已不再是最新维护点；兼容点集中在四个已定位的接口变化上。

## OUT OF SCOPE

`origin.type` 全面迁移、`httpx2` 采用、MCP 2.x 能力接入、模型目录前端展示。

## OPEN

`source` 系列 deprecated 字段的迁移时机；2.0.11 新增的 channel/SOP 能力是否需要关闭。
