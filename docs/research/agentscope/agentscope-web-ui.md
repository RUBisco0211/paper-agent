# agentscope web_ui 前端基座调研

- DATE: 2026-10-05
- STATUS: 当前（对应决策 0014、0033）

## 结论

`examples/web_ui` 是 **260 个文件的完整前端应用**，不是 demo：会话流、消息渲染、工具调用渲染、中断、凭据、工作区都已实现，直连 agent_service。`backend/` 是空壳（14 行 express，仅 `GET /api/health`），可直接删。

**改造方式**：把它的「连接层 + 会话消息链路」整段继承，在它的样式体系内叠加论文库/项目/引用三类自有页面，删掉用不到的页面（channel / mcp / skill / hub / tour / audio / knowledge）。

**四个关键改造锚点**（改这里就能接上我们的东西）：

| 需求 | 落点 |
|---|---|
| 换成 JWT 认证 | `api/client.ts` 的 `buildHeaders()`（现在写死 `X-User-ID`） |
| 会话按项目分组 | `pages/chat/index.tsx` 的会话列表分组（现在按「今天 / 更早」） |
| 引用原文卡片 | `components/chat/tool-renderers/index.tsx` 的按工具名注册的 renderer 表 |
| 登录页 | `pages/setup/index.tsx`（现在是把 `server_url` / `username` 写进 localStorage） |

## 依据

### 技术栈（`frontend/package.json`、`components.json`）

React 19 + Vite 8 + TypeScript 6 + Tailwind 4 + shadcn（`style: "radix-nova"`，baseColor `neutral`，icon `lucide`）+ TanStack Query 5 + react-router 7 + `streamdown`（Markdown，插件 code / math / cjk / mermaid）+ i18next（**自带 `zh.json`**）+ `sonner`（toast）+ `framer-motion`。

值得注意：它依赖 npm 包 **`@agentscope-ai/agentscope`**（^0.0.15），前端直接复用官方的 `Msg` / `ContentBlock` / `ToolCallBlock` / `EventType` 类型与 `appendEvent()` 累加器 —— 前端与后端的消息契约是同一份定义，不用自己对齐。

### 分层（`frontend/src/`）

| 目录 | 职责 |
|---|---|
| `api/` | 后端调用。`client.ts` 是唯一 fetch 封装；`session.ts` / `chat.ts` / `credential.ts` / `model.ts` … 按资源分文件 |
| `hooks/` | 每个资源一个 hook（`useSessions` / `useMessages` / `useAgents` / `useCredentials` …），内部用 TanStack Query |
| `components/` | `ui/`（shadcn 原语）+ `chat/`（消息与工具渲染）+ `layout/` + `dialog/` / `panel/` / `select/` |
| `pages/` | 按路由分目录：`chat` / `credential` / `knowledge` / `schedule` / `channel` / `mcp` / `skill` / `setup` |
| `context/` `lib/` `i18n/` | Upload / Audio、query-client、i18n 初始化 |

### 连接层 `api/client.ts`

- `getBaseUrl()` / `getUserId()` 从 `localStorage` 读（`server_url` / `username`），即身份是 `X-User-ID` 占位。
- 统一 `ApiError(status, detail)`，非 2xx 自动 toast（可 `silent`）；网络不通报 status `0`，超时报 `408`。
- **SSE 用 fetch + `ReadableStream` 手动解析，不用原生 `EventSource`** —— 因为要带自定义 header。见 `sessionApi.streamEvents()`：`getReader()` → 按行缓冲 → 取 `data: ` 前缀 → `JSON.parse`。`:` 开头的注释帧（心跳）跳过。

### 会话消息链路

1. `useChat().send()` = `POST /chat/`，**fire-and-forget**，只触发一次 run，不返回事件。
2. 事件全部来自 `GET /sessions/{sid}/stream`，由 `useMessages` 消费：`GET /sessions/{sid}/messages` 拉历史 → 打开 SSE → `appendEvent()` 增量累加到 `Msg`。
3. 渲染链路：`pages/chat/ChatViewport` → `components/chat/ChatContent` → `ASMessageBubble` → `Markdown`（streamdown，流式 `isAnimating`）+ `renderToolCall`。
4. 中断：`POST /sessions/{sid}/interrupt`，返回 202；前端 `ReplyPhase = idle | streaming | interrupting`。
5. 会话列表：`useSessions(agentId)` 拉 `GET /sessions/?agent_id=`，`SidebarGroup` + `SidebarGroupLabel` 分两组（今天 / 更早），行内 DropdownMenu 做改名/删除；选中态由 URL 驱动（`/chat/:agentId?/:sessionId?/:memberId?`）。

### 事件契约（`src/agentscope/event/_event.py` 的 `EventType`，26 个）

```
REPLY_START / REPLY_END
MODEL_CALL_START / MODEL_CALL_END
TEXT_BLOCK_START / TEXT_BLOCK_DELTA / TEXT_BLOCK_END
DATA_BLOCK_START / DATA_BLOCK_DELTA / DATA_BLOCK_END
THINKING_BLOCK_START / THINKING_BLOCK_DELTA / THINKING_BLOCK_END
HINT_BLOCK
TOOL_CALL_START / TOOL_CALL_DELTA / TOOL_CALL_END
TOOL_RESULT_START / TOOL_RESULT_TEXT_DELTA / TOOL_RESULT_DATA_DELTA / TOOL_RESULT_END
EXCEED_MAX_ITERS
REQUIRE_USER_CONFIRM / REQUIRE_EXTERNAL_EXECUTION
USER_CONFIRM_RESULT / USER_INTERRUPT / EXTERNAL_EXECUTION_RESULT
CUSTOM
```

`CUSTOM` 是留给我们塞自定义事件的口子；`DATA_BLOCK_*` 可承载非文本的结构化输出（引用卡片候选）。

### 工具渲染扩展点（`components/chat/tool-renderers/`）

按**工具名**注册 `ToolRenderer`，四个可选方法：`getDisplayName` / `renderConfirmBody`（HITL 确认卡）/ `renderHeader`（折叠行触发行）/ `renderBody`（展开体，`null` 表示不可展开）。未注册的工具走 `Default*`。内置了 Bash / Read / Write / Edit / Glob / Grep / TaskCreate 七个。

`ASMessageBubble` 会把**连续的** tool_call 合并成一个 `tool_call_group`（按 id 与 tool_result 配对），整组渲染。所以我们的 `search_papers` / `get_paper_excerpt` 只要注册自己的 renderer，就能在会话里渲染成引用卡片 —— 不必改消息渲染主干（这回答了 0033 的 OPEN）。

### 布局

`AppLayout` = 左侧 icon rail（`AppSidebar`，`collapsible="none"`，导航项 chat / schedule / channel / credential / mcp / skill / knowledge + 页脚语言切换 / 引导 / 设置）+ `SidebarInset` 放 `Outlet`。**会话列表不在 icon rail 上**，而在 `pages/chat/index.tsx` 的第二层 Sidebar 里 —— 所以「会话按项目分组」只改这一处，不碰 `AppSidebar`。

### 状态管理

TanStack Query：`staleTime 60s`、`retry: 1`、无轮询。会话列表 `staleTime: 0`（因为它带 `is_running`）。写操作后由对应 hook 显式 `invalidateQueries`。

## 备选方案与取舍

| 方案 | 结论 | 理由 |
|---|---|---|
| 保留 `web_ui/backend` 空壳当 BFF | 不选（0013） | 只有一个 health 路由；加一层 Node 就要两套语言与部署 |
| 用原生 `EventSource` 消费 SSE | 不可行 | 要带 `Authorization` header，`EventSource` 不支持自定义头 |
| 自己写消息渲染 | 不选（0033） | 流式、工具结果、中断 UI 是它已做好且最易出错的部分 |
| 把论文库塞进 `pages/knowledge` | 部分可用 | 页面骨架（文档列表 + 详情抽屉 + 状态轮询 `useDocumentStatusPolling`）可借鉴，但后端 KB 我们不用，数据要换成自己的 API |
| 保留它的 `schedule` 页面 | 已用于定时任务（0049） | Cron 页面已作为定时任务月视图底座 |
| 保留 i18n 双语言 | 只留 `zh` | 0014 已定 i18n 不做；`zh.json` 现成，关掉页脚语言切换即可，不要删 i18n 机制（否则所有 `t()` 调用要改） |

## 参考

- [examples/web_ui](https://github.com/agentscope-ai/agentscope/tree/main/examples/web_ui)
- 源码锚点：`frontend/src/api/client.ts`（fetch 与 SSE）、`api/session.ts`（`streamEvents`）、`hooks/useMessages.ts`（历史 + 流 + `appendEvent`）、`components/chat/ASMessageBubble.tsx`（气泡与 tool_call_group）、`components/chat/tool-renderers/index.tsx`（renderer 注册表）、`pages/chat/index.tsx`（会话列表分组）、`components/layout/AppSidebar.tsx`（icon rail）
- 后端事件定义：`src/agentscope/event/_event.py`（`EventType`）
- 相关决策：[0014 前端基于 web_ui](../../decisions/0014-frontend-on-web-ui.md)、[0033 底座 + 扩展](../../decisions/0033-frontend-extend-web-ui.md)、[0013 不做 Node BFF](../../decisions/0013-no-node-bff.md)
