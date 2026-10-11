# 0042 后续提供有界的文献原文读取工具

- DATE: 2026-10-06
- TAGS: agent, product, ingest
- STATUS: 当前
- SUPERSEDES: —

## DECISION

文献入读流程完成后，为 Agent 增加直接读取文献原文的只读工具，以 MinerU 解析并保存的 Markdown 为来源，按需返回有限片段，不默认返回整篇。读取必须受当前用户与会话的文献范围约束，与按已登记 Citation ID 回查证据的 `get_paper_excerpt` 分开。现阶段的 Agentic RAG 继续使用 `search_papers`；当前工具边界见 0026，本条所述新原文工具尚未实现。

## REJECTED

- 把 `get_paper_excerpt` 扩成任意原文读取：会混淆已登记引用回查与主动阅读。
- 一次向模型返回整篇 Markdown：长文会挤占上下文且难以控制成本。
- 允许模型传对象存储路径直接读取：绕过文献归属和会话范围校验。

## RATIONALE

检索片段适合定位相关证据；Agent 对已选中的文献还需要按需阅读更连续的原文。MinerU Markdown 已作为解析产物保存。

## OUT OF SCOPE

本次实现工具、改变当前工具白名单、整篇原文注入。

## OPEN

文献入读流程完成后确定选择片段的参数、文本预算、Markdown 缺失时的行为与引用登记关系。
