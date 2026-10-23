# 调研文档索引

按主题归档；先查本索引，再按需读取具体文档。调研是参考资料，不是现行约束；项目决定以 [决策索引](../DECISIONS.md) 与 `AGENTS.md` 为准。

## AgentScope 服务与会话（`agentscope/`）

| 文档 | 内容 |
|---|---|
| [AgentScope agent_service](agentscope/agentscope-agent-service.md) | 服务能力边界、会话流与源码锚点 |
| [AgentScope web_ui](agentscope/agentscope-web-ui.md) | 前端基座、消息渲染与扩展位置 |
| [定时 Agent 上下文](agentscope/scheduled-agent-context.md) | 定时执行的历史隔离与上下文策略对照 |

## SMUI 主题与样式（`smui/`）

| 文档 | 内容 |
|---|---|
| [SMUI 官方调研](smui/smui-theme-upstream.md) | 上游主题事实、使用建议与来源 |
| [主题迁移成本](smui/smui-theme-migration-cost.md) | 本项目前端迁移范围、成本与取舍 |
| [样式提取](smui/smui-style-extraction.md) | 集中式样式与全局变量的提取建议 |
| [迁移验收记录](smui/smui-theme-validation.md) | 验证结果、边界与深浅主题截图 |

配图：[浅色主题](smui/smui-theme-light.png) · [深色主题](smui/smui-theme-dark.png)。

## 平台技术（`platform/`）

| 文档 | 内容 |
|---|---|
| [技术栈](platform/technical-stack.md) | ORM、日志与中间件选型 |
| [SSE 传输](platform/sse-transport.md) | SSE 传输与事件模型 |

## LLM 模型与请求（`llm/`）

| 文档 | 内容 |
|---|---|
| [LLM 模型目录](llm/llm-model-catalog.md) | 模型目录与 LLM 请求层选型 |

## 文献工作流（`literature/`）

| 文档 | 内容 |
|---|---|
| [Agentero 论文工作流](literature/agentero-paper-workflow.md) | 论文解析、元数据与 Agent 工具 |
| [LLM 重排流程草案](literature/llm-as-reranker.md) | RRF 后候选重排、凭据与证据边界、待评估项；尚未实现 |

## AI 开发协作（`development/`）

| 文档 | 内容 |
|---|---|
| [AI 辅助开发工作流](development/ai-development-workflows.md) | AI 协作规范与进度管理 |
