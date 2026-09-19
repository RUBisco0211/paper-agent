# AI 请求与模型目录选型

调研日期：2026-09-19。Hugging Face Tau 固定版本：`9fe6a719ac0bda3696e9fc8413643cfe9786c73c`。AgentScope 版本：2.0.6。

## 结论

第一版继续使用 **AgentScope 原生模型层**处理请求，并直接使用它随 Provider 适配器发布的 **Model Card** 生成模型目录。

设置页保留，交互固定为：

1. 用户从目录选择 Provider；
2. 用户从该 Provider 的目录选择模型；
3. 用户只输入 API Key。

前端不提供 Provider 名称、模型 ID 或 Base URL 的自由文本输入。后端再次校验 Provider/模型组合，API Key 只随启动或恢复 Agent 的请求进入执行器，不写入业务数据或日志。

## Hugging Face Tau

这里的 Tau 是 [huggingface/tau](https://github.com/huggingface/tau)，不是 `tau2-bench`。

Tau 分为三层：`tau_ai` 提供 Provider 中立的流式调用，`tau_agent` 提供 Agent loop，`tau_coding` 提供 CLI、配置和模型选择。其内置目录位于 [`src/tau_coding/data/catalog.toml`](https://github.com/huggingface/tau/blob/9fe6a719ac0bda3696e9fc8413643cfe9786c73c/src/tau_coding/data/catalog.toml)，当前包含 28 个 Provider；目录记录显示名、模型列表、默认模型、上下文长度和凭据环境变量。

Tau 的关键设计是把两件事分开：

- `tau_ai` 负责真实请求和统一事件；
- `tau_coding` 的 TOML 目录负责 Provider/模型选项，用户凭据和默认选择另存。

目录是应用层的静态数据，不是 Provider API 的实时模型发现。Tau 支持用户用 `~/.tau/catalog.toml` 覆盖目录，但本项目首版不开放任意 Provider、模型或 Base URL。

Tau 的目录方案值得借鉴，但 `tau_ai` 不能直接作为 AgentScope 的模型对象使用。接入它需要实现 AgentScope `ChatModelBase` 适配层，并再次转换消息、工具调用和流式事件；当前没有必要形成两套模型运行时。

## AgentScope 的目录能力

AgentScope 的每个原生 Provider 同时提供 Credential、模型类、Formatter 和 Model Card。模型类的 `list_models()` 返回结构化 Model Card，包括：

- `name`：提交给 Provider 的模型 ID；
- `label`：界面显示名；
- `status` / `deprecated_at`：生命周期状态；
- `context_size` / `output_size`：上下文与输出限制；
- 输入输出类型及参数约束。

当前安装可直接构造并读取以下目录：

| Provider | AgentScope 模型类 |
|---|---|
| OpenAI | `OpenAIChatModel` |
| Anthropic | `AnthropicChatModel` |
| 阿里云百炼 | `DashScopeChatModel` |
| DeepSeek | `DeepSeekChatModel` |
| Moonshot | `MoonshotChatModel` |
| xAI | `XAIChatModel` |

Gemini 与 Ollama 在 AgentScope 中也有 Model Card 和适配器，但当前项目未安装它们的可选运行时依赖，暂不出现在目录中。

## 实现边界

- `GET /v1/llm-catalog` 从 AgentScope Model Card 返回启用的 Provider 和 active 模型。
- 设置页的 Provider 和模型都是 Select，模型选项随 Provider 联动。
- `POST /sessions/{id}/messages` 与恢复接口提交选择结果和 API Key。
- 后端拒绝目录外的 Provider 或模型，客户端不能提交 Base URL。
- AgentScope 原生 Provider 类负责请求、流式输出、工具调用格式和 Provider 感知重试。
- Agent 外层重试保持为 0，避免与模型层重试叠加。

以后需要 AgentScope 尚未支持的大量 Provider 时，再评估两条路线：为 AgentScope 增加原生适配器，或部署 LiteLLM Gateway。Tau 的目录可以作为目录结构参考，但不作为本项目运行时依赖。
