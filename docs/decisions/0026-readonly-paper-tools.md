# 0026 Agent 工具边界与库内检索行为

- DATE: 2026-10-05（2026-10-09 合并整理）
- TAGS: agent, product
- STATUS: 当前
- SUPERSEDES: 0041；`docs/overview/minimal-mvp.md` F05（已删除）

## DECISION

保留三种只读工具：`list_papers`（后端绑定会话范围，分页、有限字段）、`search_papers`（查询文本，返回证据片段、Citation ID、文献与页码、检索状态）、`get_paper_excerpt`（按已授权 Citation/Chunk 返回原文、标题路径、页码与可用定位）。模型不能通过传 `user_id` 或扩大 scope 越权。结果与展开原文都有条数与总文本预算，不把整库正文注入上下文。关键词与向量分别召回后 RRF 融合，证据去重、相邻片段合并、每篇文献配额。

AgentScope 默认工具不直接交给模型；运行时按工具类型与名称双重筛选，只装配上述库内工具、库外只读 `discover_papers`（0072）、用户确认后单次 `import_selected_papers`（0070）、浏览器执行的 `ask_user`（0075）及按当前会话范围创建定时任务的 `create_scheduled_task`（0049）。工具按功能放在 `agent_service/tools/`，经受限 Toolkit 分组；缺少任一必需工具时该轮失败，不退回默认工作区或自主任务工具。

## REJECTED

- 精简掉 `list_papers`：Agent 无从知道当前范围内有什么可查。
- 给工具加范围参数：0011 明令，范围只能在服务端注入。
- 把整库正文注入上下文：0010 的 `tool_result_limit` 会直接截断它。
- 把检索失败解释为「文献里没有相关内容」：通道降级、证据不足、整体不可用必须区分开，降级不得伪装成完整混合检索。
- 让 Agent 引用非证据集内的 Citation ID（0029）。
- 只按名称过滤默认工具或仅追加 `extra_agent_tools` 而保留 AgentScope 工作区、计划、团队等默认工具：会扩大模型能力边界。

## RATIONALE

工具集形态与重构前一致，变化只在装配方式（0011）；验收语义保持不变。

## OUT OF SCOPE

rerank（后置，见 0011）、除 0070 与 0049 外的写工具、图表工具、整库摘要。

## OPEN

单轮返回的 chunk 数与 token 预算，需与 0010 的 `tool_result_limit` 联动确定。
