# 0002 Agent 执行固定用 AgentScope 原生模型层

- DATE: 2026-09-19
- TAGS: agent
- STATUS: 已被 0006 取代（结论同向：整个 Agent 后端改用 agentscope）
- SUPERSEDES: —

## DECISION

第一版继续使用 AgentScope 原生模型层发请求，模型目录直接由各 Provider 的 Model Card 生成。设置页交互固定为三级：选 Provider → 选模型 → 填 API Key。后端再次校验 Provider/模型组合，拒绝目录外的选择。

## REJECTED

- 引入 Hugging Face Tau 的 `tau_ai` 作为请求层：它不是 AgentScope 的 `ChatModelBase`，接入要再实现一遍消息、工具调用与流式事件转换，会形成两套模型运行时。
- 部署 LiteLLM Gateway：当前 Provider 数量不需要多一层网关，只在 AgentScope 长期缺适配器时再评估。
- 开放 Base URL 或模型 ID 自由文本输入：客户端可借此绕过目录校验。
- 在 Agent 外层加重试：会与 Provider 适配器的重试叠加，外层重试保持 0。

## RATIONALE

Model Card 随适配器发布，目录与运行时天然一致，不需要另维护一份静态目录。

## OUT OF SCOPE

用户自定义 Provider、模型自选上下文字段、Gemini 与 Ollama（未安装可选运行时依赖）。

## OPEN

真实 Provider 的浏览器端到端闭环尚未验收。
