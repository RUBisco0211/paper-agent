# 0026 三个只读文献工具与检索行为

- DATE: 2026-10-05
- TAGS: agent, product
- STATUS: 当前
- SUPERSEDES: `docs/overview/minimal-mvp.md` F05（已删除）

## DECISION

保留三种只读工具：`list_papers`（后端绑定会话范围，分页、有限字段）、`search_papers`（查询文本，返回证据片段、Citation ID、文献与页码、检索状态）、`get_paper_excerpt`（按已授权 Citation/Chunk 返回原文、标题路径、页码与可用定位）。模型不能通过传 `user_id` 或扩大 scope 越权。结果与展开原文都有条数与总文本预算，不把整库正文注入上下文。关键词与向量分别召回后 RRF 融合，证据去重、相邻片段合并、每篇文献配额。

## REJECTED

- 精简掉 `list_papers`：Agent 无从知道当前范围内有什么可查。
- 给工具加范围参数：0011 明令，范围只能在服务端注入。
- 把整库正文注入上下文：0010 的 `tool_result_limit` 会直接截断它。
- 把检索失败解释为「文献里没有相关内容」：通道降级、证据不足、整体不可用必须区分开，降级不得伪装成完整混合检索。
- 让 Agent 引用非证据集内的 Citation ID（0029）。

## RATIONALE

工具集形态与重构前一致，变化只在装配方式（0011）；验收语义保持不变。

## OUT OF SCOPE

rerank（后置，见 0011）、写工具、图表工具、整库摘要。

## OPEN

单轮返回的 chunk 数与 token 预算，需与 0010 的 `tool_result_limit` 联动确定。
