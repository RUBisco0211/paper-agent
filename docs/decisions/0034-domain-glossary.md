# 0034 领域术语与禁用同义词

- DATE: 2026-10-05
- TAGS: product
- STATUS: 当前
- SUPERSEDES: `docs/CONTEXT.md`（已删除）

## DECISION

术语固定为：**Paper** 按上传 PDF 身份全局去重的文献事实，本身不授予可见性；**User Paper** 用户把 Paper 纳入个人库的关系与用户级状态边界；**Project** 从个人库汇集的命名范围；**Project Paper** 成员关系；**Ingestion Job** 一次把文献转为可检索能力的处理尝试；**Capability** 文献当前已具备的独立能力；**Chunk** 保留回到原文位置关系的可检索证据单元；**Citation** 对授权检索证据的稳定引用；**Session** 属于一个用户的对话边界。

**禁用同义词**：Paper ownership / private Paper copy、workspace / tenant / folder、Agent run / parse status、Page / MinerU block、free-form reference / bibliography item、chat room / Agent run。

## REJECTED

- 用「论文」「文档」混指：内部与界面统一为「文献」（0032）。
- 把 Project 叫 workspace 或 tenant：语义被放大成多租户。
- 把 Chunk 叫 page：Chunk 可跨页（0020）。
- 保留 Agent Run / Entry 概念：0009 与 0016 已取消。

## RATIONALE

新架构下会话与消息归 agentscope，业务侧术语必须与框架的 `Session` / `Msg` 区分开，否则重构时概念会互相污染。

## OUT OF SCOPE

代码标识符命名细则、数据库表名、术语与 agentscope 概念的映射表（暂不做）。
