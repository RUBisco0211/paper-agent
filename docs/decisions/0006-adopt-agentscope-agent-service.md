# 0006 Agent 后端核心改用 agentscope agent_service

- DATE: 2026-10-05
- TAGS: arch, agent
- STATUS: 当前
- SUPERSEDES: 0003（模块化单体七文件分层）、0005（后台任务与实时事件留在进程内）

## DECISION

Agent 后端核心改用 agentscope 的 `create_app()`（`examples/agent_service`）。会话、消息、SSE 流与 replay、中断、凭据、Agent 定义全部交给框架。业务侧自建：认证与用户、Paper / User Paper / Project / Project Paper、摄取流水线、Chunk 与混合检索、对象存储、Citation。Knowledge Base 自研，不传 `knowledge_base_manager`，`/knowledge_bases/*` 整组端点关闭。

## REJECTED

- 保留现有自建模块化单体作 Agent 核心：会话状态机、SSE 重放、中断与 HITL 都要自己维护，与框架重复。
- 用它的 Knowledge Base 承载论文：chunker 没有页码与版面定位，检索没有 RRF 混合，Citation 回查做不了。
- 自建 sessions 表只借执行器：状态机会与它的中断 / HITL 打架。
- 一次性整体重写：跑通之前整个项目不可用，且无法区分是框架问题还是自己的代码问题。

## RATIONALE

框架提供的是「多租户 Agent 后端」通用能力，与论文阅读的产品逻辑正交。复用通用部分、自建差异化部分（检索与证据定位），就是这次重构的全部收益来源。

## OUT OF SCOPE

多实例部署与 Redis 持久化、MCP 与 Skill 市场、channels（钉钉 / 飞书）、TTS、HITL 权限确认（检索工具均为只读，不写文件、不执行命令，无需沙箱）、会话分支（`messages` 为 upsert 语义，物理上不可行）。**Cron 与 Agent Team 不在此列**：它们是后置方向，不是否决项。

## OPEN

- 迁移顺序已定为「先并行跑通会话闭环、再逐步接业务」，但框架能力不满足时的回退边界未定。
- Cron 定时检索文献（0017）与 Agent Team：框架均已提供，产品上确认后置，未否决。
