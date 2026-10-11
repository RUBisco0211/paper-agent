# 代码架构

本页记录当前代码位置与依赖边界；产品取舍见 [决策索引](DECISIONS.md)，常驻禁令见 [AGENTS.md](../AGENTS.md)。

## 运行入口与数据边界

| 入口 | 职责 |
|---|---|
| `backend/app/main.py` → `app/api.py` | 业务 FastAPI，组合各业务包路由；持有业务 PostgreSQL、对象存储及摄取任务。 |
| `backend/agent_service/main.py` | 单独的 AgentScope HTTP 服务，使用自己的数据库；注入 JWT 用户身份、加密凭据和受会话范围约束的工具。 |
| `backend/app/literature_support/processing/worker.py` | 独立摄取 worker，从业务数据库领取任务，按阶段处理文献。 |
| `frontend/src/upstream/main.tsx` → `upstream/App.tsx` | React 入口与当前路由表；业务 API 和 AgentScope API 分别调用。 |

业务库与 AgentScope 库通过 `session_id` 和业务绑定关联；业务代码不直接 JOIN AgentScope 表。PDF 和 MinerU 产物存对象存储，业务库保存条目、处理状态、检索块及产物指针。

## 后端业务包

`backend/app/{auth,imports,processing,library,projects,retrieval,schedules,sessions}/` 使用七文件形态（另有 `__init__.py`）：

| 文件 | 作用与依赖边界 |
|---|---|
| `api.py` | HTTP 路由、认证依赖、调用 service、转换响应；不直接查询 repo。 |
| `schemas.py` | 请求与响应的 Pydantic 模型。 |
| `depends.py` | FastAPI 依赖装配，连接 service、repo 与外部适配器。 |
| `service.py` | 用例编排、归属校验、事务与跨包协调；不导入 HTTP 层。 |
| `domain.py` | 领域对象、枚举和局部规则；不做 I/O。 |
| `repo.py` | SQLAlchemy 表、查询与持久化；不编排用例。 |
| `ports.py` | 本包需要的外部能力契约。 |

依赖方向为 `api/depends → service → domain/repo/ports → platform`；跨业务包可使用具体仓储，不引入通用 Unit of Work。

| 包 | 管理内容 |
|---|---|
| `auth` | 用户、JWT、刷新令牌、登录会话及每用户一行的 JSONB 配置；包含工具授权偏好与浏览器时区。 |
| `library` | 全局 Paper、用户文献条目、PDF、元数据和文献读取。 |
| `imports` | DOI/arXiv 导入、库外文献发现、元数据/PDF 来源、用户确认的批量导入和入库队列。 |
| `processing` | 摄取 job 与阶段状态、重试入口；调用解析、分块、向量化流水线。 |
| `projects` | 项目及项目与用户文献条目的关系。 |
| `retrieval` | 检索块存储、授权召回、证据、引用与原文片段读取。 |
| `schedules` | AgentScope schedule 与业务用户/项目范围绑定；Agent 创建入口继承会话范围。 |
| `sessions` | AgentScope session 与业务范围绑定、引用登记和会话设置。 |

## 后端支持包与 AgentScope 服务

| 包或文件 | 管理内容 |
|---|---|
| `app/platform/` | 配置、数据库、存储（local/S3）、任务调度、安全、错误、日志；不承载业务规则。 |
| `app/literature_support/processing/` | PDF/MinerU 解析、块生成、并发 worker 与阶段执行。 |
| `app/literature_support/scholar/` | 标识符解析、Crossref/arXiv/OpenAlex 元数据、开放 PDF 来源与下载。 |
| `app/literature_support/embedding/` | 模型档案、输入批处理和 OpenAI 兼容向量接口。 |
| `app/literature_support/evidence/` | 引用定位与证据排序的纯逻辑。 |
| `app/agent/` | 业务侧模型目录支持。 |
| `agent_service/paper_agent.py` | AgentScope 智能体行为和系统提示词。 |
| `agent_service/tools/` | Agent 工具按库内文献、库外发现与入库、提问和系统功能分组；默认全部可见，写工具使用 HITL；经业务内部 HTTP API 调用。 |
| `agent_service/schedule_api.py` | 内部任务创建接口，继承 AgentScope 会话模型配置并启用任务。 |
| `agent_service/auth.py`、`credential_storage.py` | 用户认证与加密凭据存储适配。 |

`app/conversation/` 目前没有实现文件，不作为新代码锚点。

## 前端

| 目录 | 作用 |
|---|---|
| `src/upstream/App.tsx` | 当前路由表和受保护的应用布局。 |
| `src/upstream/components/layout/` | 全局图标栏、页面容器和入口间保活。 |
| `src/upstream/pages/chat/`、`schedule/`、`imports/` | 基于 AgentScope web_ui 扩展的对话、定时任务与入库队列。 |
| `src/upstream/components/chat/`、`ui/`、`src/upstream/api/` | web_ui 消息与表单组件、基础 UI、AgentScope API 客户端。 |
| `src/pages/` | 业务路由页面：文献库、阅读、在线检索、项目、设置与登录。 |
| `src/components/{chat,papers,projects}/` | 业务复合组件；部分弹窗、详情和 PDF 组件目前直接使用 `useApi`/`useQuery`，弹窗视觉使用 upstream 的 Dialog/Button。 |
| `src/components/ui/` | 项目扩展的展示原语；与 upstream 的组件职责区分。 |
| `src/lib/api/` | 业务服务 HTTP/SSE 客户端、端点和类型；不承载组件。 |
| `src/lib/auth/`、`src/lib/settings/`、`src/lib/theme/` | 登录态、设置和主题状态。 |
| `src/test/` | 前端测试公共设施，测试文件紧贴被测页面或组件。 |

新业务页面放 `src/pages/`，需要沿用 web_ui 会话/任务布局时放对应 `src/upstream/pages/`。`AGENTS.md` 目前要求页面负责取数、组件只负责展示；现有业务复合组件中的直接取数是待确认的规范与代码差异，不应当在新代码中照搬。路由以 `src/upstream/App.tsx` 为准，不把遗留入口文件当作当前路由表。
