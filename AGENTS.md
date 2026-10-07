# AGENTS.md

> 每次会话自动读取。本项目唯一的常驻约束文件。
> 决策 → `docs/DECISIONS.md`（索引）+ `docs/decisions/NNNN-*.md`（正文）
> 调研 → `docs/research/`
> 流程总纲 → `WORKFLOW.md`，你不需要读它。
> 超过 200 行时，把最长的一节抽成 `docs/xxx.md`，并在第 12 节登记。

## 1. 项目与背景

Paper Agent 管理个人论文库、项目范围与基于论文证据的 Agent 阅读会话；多用户系统，每个用户的数据与交互彼此隔离。

- 阶段：MVP 功能 F01–F09 已实现；2026-10 起按决策 0006–0016 重构为 agentscope 后端，**R1–R7 自动门禁与 R8 DeepSeek 浏览器主路径已通过；R8 服务端多页 PDF 与真实会话并行已回测，浏览器无刷新断线恢复、检索故障、内嵌 PDF 和并行交互待回测**
- 规模：单机 Docker Compose，个人自用，并发 <10，论文库千篇量级
- 用户：研究者本人在浏览器里完成入库 → 组织范围 → 问答 → 打开原文核对引用
- 硬约束：单机部署（PostgreSQL 16 + pgvector、本地或 S3 对象存储）；**无 Redis / Celery**（解析走独立 worker 进程，由 DB 协调）；LLM API Key 由 Credential 系统持有、不进日志
- **明确不做**：多实例部署；会话分支（框架 `messages` 为 upsert 语义）；历史编辑；跨会话历史合并；精确区域高亮与图表交互；标题/关键词联网搜论文；GROBID；多解析器回退；Agent 写工具；HITL 权限确认与沙箱；MCP/Skill 市场、channels、TTS
- **已扩展**：Cron 定时任务支持全局或项目范围与一周内选日（0049）。
- **后置（MVP 之后，非否决）**：Agent Team（0006）、rerank（0011）、历史导出（0009）。这些**不是不做**，评估时不要当成已否决。

你默认按"生产级 + 高规模"写代码。「阶段」和「规模」两行是唯一能纠正你的东西。

## 2. 分层与依赖方向

后端依赖只能从左指向右，反向一律禁止：

```
api.py → service.py → domain.py / repo.py / ports.py → platform/
```

| 目录 | 职责 | 不该放 |
|---|---|---|
| `backend/app/<业务包>/api.py` | HTTP 路由、认证依赖、调 service、响应转换 | 直接查 repo、写 SQLAlchemy 查询 |
| `.../service.py` | 用例编排、资源归属检查、事务协调 | 导入 FastAPI |
| `.../domain.py` | 领域对象、枚举、局部业务规则 | 外部 I/O |
| `.../repo.py` | SQLAlchemy 表、查询与持久化 | 业务编排 |
| `.../ports.py` | 本包用到的外部能力契约 | 具体适配器实现 |
| `.../depends.py`、`schemas.py` | HTTP 装配、请求响应模型 | 业务规则 |
| `backend/app/platform/` | 配置、数据库、存储、调度、日志、错误、安全 | 业务规则 |
| `frontend/src/pages/` | 路由页面、取数与状态编排 | 可复用展示组件 |
| `frontend/src/components/` | 展示组件（不含取数） | `lib/api` 调用 |
| `frontend/src/lib/api/` | HTTP 与 SSE 客户端 | 组件与样式 |

业务包固定七文件：`api / schemas / depends / service / domain / repo / ports`。模块化单体，跨业务包可直接用对方的具体仓储，不引入完整 Unit of Work。

## 3. 模式锚点

新增代码照着已有文件写，不要另起炉灶。路径必须真实存在。

- 新增后端业务包 → 照 `backend/app/library/`（api/service/domain/repo/schemas/depends/ports）
- 新增后端支持包 → 照 `backend/app/processing/`（纯函数 + 有状态类，不凑统一外观）
- 新增 Agent 工具 → 照 `backend/agent_service/retrieval_tools.py`
- 新增后端测试 → 照 `backend/tests/library/test_upload.py`
- 新增前端页面 → 照 `frontend/src/pages/session-workspace.tsx`
- 新增前端组件 → 照 `frontend/src/components/chat/message-thread.tsx`
- 新增前端测试 → 照 `frontend/src/components/chat/message-thread.test.tsx`

## 4. 外部依赖

| 依赖 | 用途 | 失败时的行为 |
|---|---|---|
| PostgreSQL + pgvector | 业务数据与向量检索 | 启动即失败，不降级 |
| MinerU | PDF 正文解析 | 阶段置失败，保留 PDF 与条目，允许重试，不阻断其他阶段 |
| Embedding（DashScope `text-embedding-v3` / TEI） | Chunk 向量 | 检索退化为仅关键词，**并在响应中标明**，不伪装成混合检索 |
| LLM Provider（AgentScope） | Agent 回答 | 折成稳定错误码：`llm_not_configured` / `provider_rate_limited` / `agent_timeout` / `agent_max_iters` / `agent_unavailable` |
| 对象存储（local / S3） | PDF、解析产物、Entry JSONL | 上传失败即报错，不静默丢弃 |
| Zotero recognizer、Crossref / arXiv | 元数据补全与全文获取 | 尽力而为，失败保留占位条目；DOI/arXiv 导入终态可为 `pdf_unavailable` |

「失败时的行为」不写，你会默认吞掉异常。

## 5. Never do（违反即返工）

- 禁止 Router 直接导入 `repo` 或 SQLAlchemy 查询，必须经 `service`。
- 禁止 `service` / `domain` / `repo` / `ports` 反向导入 `api`、`schemas`、`depends` 或 FastAPI。
- 禁止使用旧模块路径（`dependencies` / `application` / `persistence`），不保留兼容壳。
- 禁止把 LLM API Key 写进日志、对象存储或任务队列（Key 由 Credential 系统持有，见 0015）。
- 禁止业务侧直接 JOIN 或依赖 agentscope 的表结构；跨边界一律用 `session_id` 在应用层拼接（0007）。
- 禁止把 citation 塞进 `Msg.payload` 的自定义字段，只能放 `Msg.metadata`（0009）。
- 禁止给 Agent 工具加"范围"参数，范围只能由 `extra_agent_tools` 工厂在服务端注入。
- 禁止让引用脱离已登记证据，Citation 必须能回查到原文片段与页码。
- 禁止用户 A 的数据出现在用户 B 的响应里；每个查询都要带归属校验。
- 禁止改前端代码或文案前不读 `docs/decisions/0032-ui-copy-rules.md` 与 `0033-frontend-extend-web-ui.md`。
- 禁止业务弹窗使用浏览器原生确认框或自有 Dialog/AlertDialog；统一使用 web_ui 的 Dialog 与 Button（0055）。
- 禁止"顺手重构"无关的相邻代码。改动严格限定在本任务。
- 禁止新增依赖前不检查是否已有同类。
- 禁止为了让测试变绿而修改测试。测试红了说明实现错了。
- 禁止留下 TODO 或空 `except`。
- 禁止把未实现的桩写成已完成；范围与状态以 `docs/decisions/` 与实际代码为准。
- 禁止把 Token、Cookie、密码、完整请求体、文献原文或模型提示词写进日志。
- 禁止写背景介绍、复述需求、"首先 / 其次 / 最后"式散文。
- 禁止输出文档全文，更新只输出 diff。

## 6. 工作方式

- 能从代码库查到的事实，自己查，不要问我。
- 不确定这段该放哪一层时，先问，不要猜。
- 真的需要我决策：一次只问一个，给 A/B/C 选项 + 你的推荐 + 一句话理由。
- 不要为了推进而猜。猜错的代价比问我高。

## 7. 实现前：design 门控

命中任一情况，**先输出 ≤30 行的 design 等我确认，不要直接写代码**：

- 新增模块 / 对外接口、修改数据模型或 schema、跨层调用、引入新依赖
- 改动 Agent 工具契约、引用模型或会话范围语义
- 你不确定这段代码该放在哪一层

design 只允许四个字段，不许增加：

```
## 放哪       涉及文件，属于哪一层
## 行为       ≤5 条，只写 what，不写 how
## 边界       准备测哪些边界
## 不做什么   out of scope
```

## 8. 测试纪律

- 测试跟着行为走，不跟着函数走。一个测试只能有一个 reason to fail。
- 测试名是完整句子：`<主体> <行为> when <条件>`，不是 `test_<函数名>`。
- **测试第一次必须是红的**。第一次就全绿，说明你在描述已有代码，重写。
- 后端测试跑真实 PostgreSQL（`docker compose up -d postgres`），不允许 mock 掉数据库语义。
- 测试必须快且确定。不允许 flaky，不允许依赖真实网络（真实 Provider 联调除外，须显式标注）。
- 前端测试用 `frontend/src/test/` 下的既有设施，不新造测试框架。

## 9. 完成标准（缺一不可）

1. 后端 `cd backend && uv run pytest -q` 通过。
2. 前端 `cd frontend && pnpm run typecheck && pnpm run test && pnpm run build` 通过。
3. 没有修改本任务范围外的文件。
4. 没有新增被吞掉的异常，没有留下 TODO。
5. 对外行为有变化时，本文件或 `docs/decisions/` 已同步更新。

## 10. 收尾：`/clear` 之前必须做

扫描本次会话，输出三块**增量**（只输出新增，绝不重写整个文件）：

1. **新增禁令** → 本文件第 5 节。来源：我纠正过 ≥2 次的事、被回滚过的写法、我明确说过"不要这样"的地方。每条一行 `禁止 ...`，必须**可判定**。
2. **新增决策** → `docs/decisions/NNNN-*.md` + 在 `docs/DECISIONS.md` 索引补一行。**REJECTED 不能空**，两个文件一次输出。
3. **待办与风险** → 直接告诉我。

硬规则：

- 只输出 diff，每条 ≤1 行。
- **没内容就输出「无」，不许编造**。
- 不确定该不该记的，问我，不要自己决定。

## 11. 上下文纪律

- 一个 task 一个干净会话，任务完成后 `/clear`。
- 小 bug 修复开新会话，只带相关文件 + 报错，不要带整段历史。
- **我第三次纠正你同一件事时，停下来** —— 那说明这条规则该写进第 5 节，而不是让我再说一遍。
- `/compact` 后必须保留：已修改文件清单、测试结论、待确认的 design、未解决决策。

## 12. 按需加载

### A. 约束类（等同于第 5 节，命中就必须遵守）

| 触发场景 | 读 |
|---|---|
| **改动 Agent 后端、会话、检索或凭据接入** | `docs/DECISIONS.md` 中 0006–0017、0035、0049，再按需读 `docs/research/agentscope-agent-service.md` |
| **改动产品功能范围、文献 / 摄取 / 引用行为** | `docs/DECISIONS.md` 中 0018–0034 |
| **改任何前端代码或文案** | 0014（基座）、0032（文案）、0033（沿用与扩展的边界）、0045（页面布局）、0048（任务入口）、0049（定时任务范围与频率）、0055（业务弹窗） |
| 涉及命名与领域术语 | 0034 |
| 改后端日志事件名或错误码 | 无独立规范，见第 5 节；日志规范待业务服务定稿后另立条目 |

### B. 参考类（按需下钻，先索引后读）

| 触发场景 | 读 |
|---|---|
| 需要某条决策的细节 | 先读 `docs/DECISIONS.md` 索引，再只读那一条 `docs/decisions/NNNN-*.md` |
| 涉及已调研过的主题 | `docs/research/` 下对应文件（技术栈 / SSE / LLM 模型目录 / Agentero / AI 开发工作流 / **agentscope agent_service** / **agentscope web_ui 前端基座**） |

### C. 工作态（生命周期有限，重构完成后删除）

根目录 `TODO.md` 是重构期间的任务清单，只回答「做什么、怎么算做完」，**不是规范、不是决策来源**。开工重构任务前读一次，不要在其中找约束或理由。

`docs/` 下只有 `DECISIONS.md`、`decisions/`、`research/` 三处，没有第四处。

- **禁止 glob 或批量读取** `docs/decisions/` 和 `docs/research/`。先索引，后下钻。
- 调研文档是参考资料，不是约束。其中内容只有写进第 5 节或 `docs/decisions/` 才对你生效。
