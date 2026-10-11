# 0006 Agent 后端核心改用 agentscope agent_service

- DATE: 2026-10-05（2026-10-09 合并整理）
- TAGS: arch, agent
- STATUS: 当前
- SUPERSEDES: 0002（模型层）、0003 中 Agent/会话层、0005（进程内解析与事件）

## DECISION

Agent 后端核心改用 agentscope 的 `create_app()`（`examples/agent_service`）。会话、消息、SSE 流与 replay、中断、凭据、Agent 定义全部交给框架。业务侧自建：认证与用户、Paper / User Paper / Project / Project Paper、摄取流水线、Chunk 与混合检索、对象存储、Citation。Knowledge Base 自研，不传 `knowledge_base_manager`，`/knowledge_bases/*` 整组端点关闭。

模型请求使用 AgentScope 原生模型层；模型目录来自 Provider Model Card。设置页选择 Provider、模型与 Credential，服务端再次校验组合；不开放任意 Base URL 或模型 ID。解析由独立数据库队列 worker 执行（见 0056），实时事件由 AgentScope 持有。

## REJECTED

- 保留现有自建模块化单体作 Agent 核心：会话状态机、SSE 重放、中断与 HITL 都要自己维护，与框架重复。
- 用它的 Knowledge Base 承载论文：chunker 没有页码与版面定位，检索没有 RRF 混合，Citation 回查做不了。
- 自建 sessions 表只借执行器：状态机会与它的中断 / HITL 打架。
- 一次性整体重写：跑通之前整个项目不可用，且无法区分是框架问题还是自己的代码问题。
- 再引入 `tau_ai` 模型运行时、LiteLLM Gateway 或 Agent 外层重试：会重复模型适配、工具流式事件或 Provider 重试。

## RATIONALE

框架提供的是「多租户 Agent 后端」通用能力，与论文阅读的产品逻辑正交。复用通用部分、自建差异化部分（检索与证据定位），就是这次重构的全部收益来源。

## OUT OF SCOPE

多实例部署与 Redis 持久化、MCP 与 Skill 市场、channels（钉钉 / 飞书）、TTS、通用 HITL 权限确认与沙箱、会话分支（`messages` 为 upsert 语义）。用户确认的批量入库是 Agent 写工具的已批准例外（0070）；Agent Team 为后置方向。定时任务已实现（0049）。

## OPEN

- Agent Team 的产品形态与框架能力不满足时的回退边界未定。
