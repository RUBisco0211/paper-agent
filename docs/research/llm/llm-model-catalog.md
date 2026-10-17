# 模型目录与 LLM 请求层

- DATE: 2026-09-19（本次改写仅压缩结构，未更新结论）
- STATUS: 当前

## 结论

第一版用 **AgentScope 原生模型层**发请求，模型目录直接由各 Provider 的 Model Card 生成。设置页固定三级交互：选 Provider → 选模型 → 填 API Key。前端不提供 Provider 名称、模型 ID、Base URL 的自由文本输入；后端二次校验 Provider/模型组合。

AgentScope 每个原生 Provider 同时提供 Credential、模型类、Formatter 和 Model Card，`list_models()` 返回 `name` / `label` / `status` / `deprecated_at` / `context_size` / `output_size` / 参数约束。当前可直接构造的目录：OpenAI、Anthropic、DashScope、DeepSeek、Moonshot、xAI。Gemini 与 Ollama 未装可选运行时依赖，不进目录。

实现边界：`GET /v1/llm-catalog` 返回启用 Provider 与 active 模型；模型选项随 Provider 联动；Provider 原生类负责请求、流式、工具调用格式与 Provider 感知重试；**Agent 外层重试保持 0**。

## 依据

目录随适配器发布，与运行时天然一致，不需要另维护一份静态目录。Tau 的 `catalog.toml` 值得作为目录结构参考，但 `tau_ai` 不是 AgentScope 的 `ChatModelBase`，接入要再实现消息、工具调用与流式事件转换。目录是应用层静态数据，不是 Provider API 的实时模型发现。

## 备选方案与取舍

| 方案 | 结论 | 理由 |
|---|---|---|
| Hugging Face Tau `tau_ai` 作请求层 | 不选 | 需自写 `ChatModelBase` 适配层，会形成两套模型运行时 |
| LiteLLM Gateway | 暂不 | 等 AgentScope 长期缺适配器时再评估 |
| 开放 Base URL / 模型 ID 输入 | 禁止 | 客户端可绕过目录校验 |
| `tau_coding` 的 TOML 目录 | 只作结构参考 | 首版不开放任意 Provider 与 `~/.tau/catalog.toml` 覆盖 |

## 参考

- [AgentScope](https://github.com/agentscope-ai/agentscope)（版本 2.0.6）
- [huggingface/tau](https://github.com/huggingface/tau)（固定版本 `9fe6a71`）· [catalog.toml](https://github.com/huggingface/tau/blob/9fe6a719ac0bda3696e9fc8413643cfe9786c73c/src/tau_coding/data/catalog.toml)
