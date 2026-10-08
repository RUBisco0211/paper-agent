# 0041 Agent 运行时只开放文献只读工具

- DATE: 2026-10-06
- TAGS: agent, security
- STATUS: 已被 0069 取代
- SUPERSEDES: —

## DECISION

AgentScope 每轮装配的默认工具不直接交给模型；自定义 Agent 仅保留服务端注入的 `list_papers`、`search_papers`、`get_paper_excerpt`。其中 `search_papers` 是当前 Agentic RAG 的内容检索工具，按会话范围进行关键词与 embedding 召回、融合并返回可回查证据。缺少任一工具时该轮失败，不退回默认工具集。

## REJECTED

- 只用 `extra_agent_tools` 注入三个工具：AgentScope 仍会同时装配工作区、计划、定时、团队等默认工具。
- 仅按工具名称过滤：同名非业务工具可能绕过边界。
- 为当前 MVP 另建一套 RAG 工具：现有 `search_papers` 已有检索与证据链路。

## RATIONALE

默认工具集包含 MVP 未开放的写入和自主任务能力；按工具类型与名称双重筛选，使模型调用边界与产品范围一致。

## OUT OF SCOPE

后续检索质量优化、rerank、写工具、Cron 与 Agent Team。

## OPEN

无。
