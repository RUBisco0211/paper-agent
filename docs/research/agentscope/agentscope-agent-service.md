# agentscope agent_service 能力边界调研

- DATE: 2026-10-05
- STATUS: 当前（对应决策 0006–0016）

## 结论

`examples/agent_service` 不是示例代码，是 `create_app()` 一行生成的多租户 Agent 后端框架（`main.py` 177 行，全是配置）。

**能直接拿走**：Session 与会话状态、SSE 流 + replay + 多订阅者、中断 / HITL / 权限、Credential（API Key）、Agent 定义、Workspace 文件目录、Cron 调度、Agent Team。

**必须自建**：认证与用户体系、Paper / User Paper / Project / Project Paper、摄取流水线、Chunk 与混合检索（FTS + pgvector + RRF）、对象存储、Citation 登记与回查。

## 依据

### 存储是三层，互相独立

| 层 | 作用 | 内置实现 |
|---|---|---|
| `Storage` | 持久化，必填。13 张表：`credentials / agents / sessions / messages / schedules / teams / sops / sop_runs / knowledge_bases / knowledge_documents / mcps / skills / channels` | `RedisStorage`、`AsyncSQLAlchemyStorage`（SQLite / PG / MySQL，自带 Alembic） |
| `MessageBus` | **运行时通道，不是持久化**。存会话锁、replay log、inbox 队列、唤醒信号 | `RedisMessageBus`、`InMemoryMessageBus` |
| Workspace / BlobStore / VectorStore | 文件工作目录、KB 文件字节句柄（`blob_uri`）、向量库（`QdrantStore`） | 多种 |

**Redis 不是硬要求**：单实例用 `AsyncSQLAlchemyStorage` + `InMemoryMessageBus`，零 Redis；只有多进程 / 多节点才必须 Redis。

存储模型不是传统关系表，是「JSON payload + 提升索引列」：`id / created_at / updated_at` 是信封列，其余塞 JSONB，只有需要查询的字段（`user_id`、`status`、`lease_expires_at`）才提升成真实列并建索引。**所有表都没有前缀**，`sessions` / `messages` 与业务 ER 图同名。

`messages` 表特殊：注释原文 *messages are not stand-alone records — they are per-session events*，主键是复合键 `(session_id, msg_id)`，同一 key 再写是 **replace 不是 append**（继承 `RedisStorage.upsert_message` 语义）。因此分支语义天然不支持。

### 模型变化与上下文压缩

- **模型变化没有事件**。`PATCH /sessions/{id}` 传 `chat_model_config={credential_id, model}` 覆盖写入；运行期间改返回 409（agent 在 run 开始时快照 config，中途改也会被忽略，且会与 run 的状态持久化竞争）。
- **上下文压缩有，且在 `agent/_config.py` 的 `ContextConfig`**：`trigger_ratio`(≤0.9) / `reserve_ratio` / `context_buffer_ratio` / `tool_result_limit` / `compression_prompt` / `summary_template` / `summary_schema`。自动流程：统计 token → 判阈值 → 分割（工具调用与结果对不拆散）→ 模型生成结构化摘要 → 替换旧消息。也有 `compress_context()` 手动触发与 `on_compress_context` middleware hook、`compression_tool_enabled`（让 agent 自己调工具压缩）。
- **压缩不写 `messages` 表**：`_service/_chat.py` 里没有任何压缩相关代码，它是 agent 进程内的上下文管理。所以历史消息完整保留，只是模型看到的是「摘要 + 最近消息」。

### 认证

`app/deps.py` 的默认实现是读 `X-User-ID` header，注释原文 *Temporary header-based identity; will be replaced by JWT auth*。覆盖方式：`app.dependency_overrides[get_current_user_id] = ...`。文档明确「没有内置用户认证系统，部署前必须替换」。

### 范围注入

不传 `knowledge_base_manager` 时 `/knowledge_bases/*` 整组端点关闭，`SessionConfig.knowledge_config.knowledge_base_ids` 也失效。AgentScope 2.0.6 的检索工具注入点是 `extra_agent_tools`：`(user_id, agent_id, session_id) -> awaitable[list[ToolBase]]`，不提供浏览器请求的 Bearer token。

### 会话流是「触发」与「消费」分离

`POST /chat/` 只触发一次 run（fire-and-forget，不返回事件）；事件一律来自 `GET /sessions/{sid}/stream`（SSE），历史走 `GET /sessions/{sid}/messages`。中断是 `POST /sessions/{sid}/interrupt`（202）。

事件类型见 `src/agentscope/event/_event.py` 的 `EventType`（26 个）：`REPLY_*` / `MODEL_CALL_*` / `TEXT_BLOCK_*` / `DATA_BLOCK_*` / `THINKING_BLOCK_*` / `HINT_BLOCK` / `TOOL_CALL_*` / `TOOL_RESULT_*` / `EXCEED_MAX_ITERS` / `REQUIRE_USER_CONFIRM` / `USER_INTERRUPT` / `CUSTOM`。其中 `CUSTOM` 与 `DATA_BLOCK_*` 是承载自定义结构化输出（例如引用卡片）的口子。

前端如何消费这份契约见 [agentscope-web-ui.md](agentscope-web-ui.md)（SSE 用 fetch + `ReadableStream` 而非 `EventSource`，因为要带自定义头）。

### web_ui 是完整前端，不是 demo

260 个文件，直连 agent_service；`backend` 是空壳 —— 14 行 express，只有一个 `GET /api/health`，依赖仅 express + cors，**它不是 BFF，也不是认证层**，是留给使用者的占位。技术栈 React 19 + Vite + Tailwind 4 + shadcn（`radix-nova` 方言）。完整调研（分层、连接层、消息渲染链路、工具渲染扩展点、布局与改造锚点）另见 [agentscope-web-ui.md](agentscope-web-ui.md)。

## 备选方案与取舍

| 方案 | 结论 | 理由 |
|---|---|---|
| 用它的 Knowledge Base 承载论文 | 不选 | chunker 无页码 / 版面定位，检索无 RRF 混合，Citation 回查做不了 —— 这是本项目的差异化所在 |
| `RedisStorage` + `RedisMessageBus` | 不选 | 多实例才需要；MessageBus 不是持久化层，单机用 `InMemoryMessageBus` 即可 |
| 自建 sessions 表只借执行器 | 不选 | 状态机会与它的中断 / HITL 打架 |
| 检索走 MCP server | 不选 | 每次调用多一跳，且范围隔离要在 MCP 侧另做一层（传参可被模型伪造） |
| 自建 entries 表 | 不选 | 与 `messages` 双写，一致性成本与侵入性都高；压缩本来就不写历史 |
| 一次性整体重写 | 不选 | 跑通前整个项目不可用，无法区分是框架问题还是自己的代码问题 |

## 参考

- [examples/agent_service](https://github.com/agentscope-ai/agentscope/tree/main/examples/agent_service)
- [examples/web_ui](https://github.com/agentscope-ai/agentscope/tree/main/examples/web_ui)
- [Context / ContextConfig 文档](https://docs.agentscope.io/en/versions/2.0.4/building-blocks/context)
- 源码锚点：`app/storage/_model/_session.py`、`app/storage/_sql/_tables.py`（`MessageRow`）、`agent/_config.py`（`ContextConfig`）、`agent/_agent.py`（`compress_context`）、`app/deps.py`（`get_current_user_id`）、`app/_router/_session.py`（`PATCH /{session_id}`）、`event/_event.py`（`EventType`）
- 配套调研：[agentscope web_ui 前端基座](agentscope-web-ui.md)
