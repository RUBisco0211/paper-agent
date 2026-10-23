# 代码架构

本页记录当前代码位置与依赖边界；产品取舍见 [决策索引](DECISIONS.md)，常驻禁令见 [AGENTS.md](../AGENTS.md)。

## 运行入口与数据边界

| 入口                                                  | 职责                                                                                                                                                           |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/app/main.py` → `app/api.py`                  | 业务 FastAPI，组合各业务包路由；持有业务 PostgreSQL、对象存储及摄取任务。                                                                                      |
| `backend/agent_service/main.py`                       | 单独的 AgentScope HTTP 服务，使用自己的数据库；注入用户身份、加密凭据和受会话范围约束的工具；0081 要求认证逐请求经 HTTP 回查业务登录态，不直接访问业务用户表。 |
| `backend/app/literature_support/processing/worker.py` | 独立摄取 worker，从业务数据库领取任务，按阶段处理文献。                                                                                                        |
| `frontend/src/main.tsx` → `src/app/App.tsx`           | React 入口与当前路由表；业务 API 和 AgentScope API 分别调用。                                                                                                  |

业务库与 AgentScope 库通过 `session_id` 和业务绑定关联；业务代码不直接 JOIN AgentScope 表。PDF 和 MinerU 产物存对象存储，业务库保存条目、处理状态、检索块及产物指针。

## 后端业务包

`backend/app/{auth,imports,processing,library,projects,retrieval,schedules,sessions}/` 使用七文件形态（另有 `__init__.py`）：

| 文件         | 作用与依赖边界                                                 |
| ------------ | -------------------------------------------------------------- |
| `api.py`     | HTTP 路由、认证依赖、调用 service、转换响应；不直接查询 repo。 |
| `schemas.py` | 请求与响应的 Pydantic 模型。                                   |
| `depends.py` | FastAPI 依赖装配，连接 service、repo 与外部适配器。            |
| `service.py` | 用例编排、归属校验、事务与跨包协调；不导入 HTTP 层。           |
| `domain.py`  | 领域对象、枚举和局部规则；不做 I/O。                           |
| `repo.py`    | SQLAlchemy 表、查询与持久化；不编排用例。                      |
| `ports.py`   | 本包需要的外部能力契约。                                       |

依赖方向为 `api/depends → service → domain/repo/ports → platform`；跨业务包可使用具体仓储，不引入通用 Unit of Work。

| 包           | 管理内容                                                                               |
| ------------ | -------------------------------------------------------------------------------------- |
| `auth`       | 用户、JWT、刷新令牌、登录会话及每用户一行的 JSONB 配置；包含工具授权偏好与浏览器时区。 |
| `library`    | 全局 Paper、用户文献条目、PDF、元数据和文献读取。                                      |
| `imports`    | DOI/arXiv 导入、库外文献发现、元数据/PDF 来源、用户确认的批量导入和入库队列。          |
| `processing` | 摄取 job 与阶段状态、重试入口；调用解析、分块、向量化流水线。                          |
| `projects`   | 项目及项目与用户文献条目的关系。                                                       |
| `retrieval`  | 检索块存储、授权召回、证据、引用与原文片段读取。                                       |
| `schedules`  | AgentScope schedule 与业务用户/项目范围绑定；Agent 创建入口继承会话范围。              |
| `sessions`   | AgentScope session 与业务范围绑定、引用登记和会话设置。                                |

## 后端支持包与 AgentScope 服务

| 包或文件                                         | 管理内容                                                                                                            |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| `app/platform/`                                  | 配置、数据库、存储（local/S3）、任务调度、安全、错误、日志；不承载业务规则。                                        |
| `app/literature_support/processing/`             | PDF/MinerU 解析（远程 API）、块生成、并发 worker 与阶段执行。                                                                   |
| `app/literature_support/scholar/`                | 标识符解析、Crossref/arXiv/OpenAlex 元数据、开放 PDF 来源与下载。                                                   |
| `app/literature_support/embedding/`              | 模型档案、输入批处理和 OpenAI 兼容向量接口（远程 bge-m3）。                                                                        |
| `app/literature_support/evidence/`               | 引用定位与证据排序的纯逻辑。                                                                                        |
| `app/agent/`                                     | 业务侧模型目录支持。                                                                                                |
| `agent_service/paper_agent.py`                   | AgentScope 智能体行为和系统提示词。                                                                                 |
| `agent_service/tools/`                           | Agent 工具按库内文献、库外发现与入库、提问和系统功能分组；默认全部可见，写工具使用 HITL；经业务内部 HTTP API 调用。 |
| `agent_service/schedule_api.py`                  | 内部任务创建接口，继承 AgentScope 会话模型配置并启用任务。                                                          |
| `agent_service/auth.py`、`credential_storage.py` | 用户认证与加密凭据存储适配。                                                                                        |

`app/conversation/` 目前没有实现文件，不作为新代码锚点。

## 邮件部署边界（0081 已批准，功能验收另记）

- `backend/app/platform/mail_worker.py` 是批准的独立入口，通过 `python -m app.platform.mail_worker` 运行；`start.sh` 已纳入启动、退出监视、cleanup 与 `.var/logs/mail-worker.log`。业务实现与 AgentScope 通知 hook 由主 agent/其他负责人集成，不以本页声明实现或测试完成。
- 业务 PostgreSQL 持久 outbox 保存待投递邮件及状态；独立邮件进程领取并经 SMTP 投递，失败保留状态，不引入 Celery。最终回答快照仅供投递，不成为第二份运行会话历史；AgentScope 仍持有 schedules、sessions/messages。
- Redis 只负责邮箱临时验证、用途绑定的一次性凭证及冷却/限流；不是账号、登录会话、用户配置或邮件队列存储。Compose 使用 `redis:7-alpine`，使用标准 `6379`；本机不得再运行第二个 Redis，应用不得连接宿主机 Redis。启动脚本校验宿主机连接与容器 `run_id`，不一致即失败。默认不持久化，状态丢失须重新验证。
- 注册、找回与登录会话撤销仍由 `auth` 编排；任务邮件开关与归属由 `schedules` 负责，默认关闭且只发所属用户的已验证邮箱，Agent 不指定收件地址。通知时机与最终结果通过 AgentScope 边界集成，不 JOIN 其表。
- SMTP 与 `REDIS_URL`、`PUBLIC_APP_URL` 从后端 settings 配置；QQ SMTP 授权码仅由主 agent 写入不提交的 `backend/.env`。根 `.env` 单独保留 Compose 插值配置，不与后端环境文件合并。
- 业务 API 使用源码已有的公开 `/health`；当前 AgentScope `/health` 要求认证，启动脚本只检查其进程/TCP，不伪造 JWT、不加生产认证绕过。TCP 就绪不宣称完整健康；新增公共 Agent 健康端点须由主 agent 另行协调。

## 前端

| 目录                                     | 作用                                                                  |
| ---------------------------------------- | --------------------------------------------------------------------- |
| `src/app/App.tsx`                        | 当前路由表和受保护的应用布局。                                        |
| `src/pages/`                             | 业务路由页面：文献库、阅读、在线检索、登录、对话与定时任务入口。      |
| `src/pages/chat/`、`schedule/`           | 基于 web_ui 扩展的对话与定时任务页面。                                |
| `src/components/ui/`                     | 全部基础展示原语（web_ui 基座，加上卡片与滚动区的项目扩展）。         |
| `src/components/chat/`                   | 消息渲染、输入、工具调用渲染、引用与对话侧栏。                        |
| `src/components/layout/`、`markdown/`    | 布局骨架、入口间保活与共享 Markdown 渲染器。                          |
| `src/components/schedule/`、`imports/`   | 定时任务对话框/详情、日历网格与入库队列面板。                         |
| `src/components/providers/`              | 应用级 React Provider（API、认证、主题、Agent UI、入库队列、音频）。  |
| `src/components/{papers,projects}/`      | 业务复合组件；部分弹窗、详情和 PDF 组件直接使用 `useApi`/`useQuery`。 |
| `src/lib/api/`                           | 业务服务 HTTP 客户端、端点与请求封装。                                |
| `src/lib/api/agentscope/`                | AgentScope HTTP/SSE 客户端与端点。                                    |
| `src/types/`                             | 前端通用类型：业务、AgentScope、调度、会话与聊天引用。                |
| `src/hooks/`、`src/i18n/`、`src/assets/` | 跨页面 hooks、文案资源与静态资源。                                    |
| `src/lib/{auth,settings,hooks,papers}/`  | 登录态令牌、设置、通用 hooks 与论文词表。                             |
| `tests/`                                 | 前端测试，按 `src/` 结构镜像；公共设施在 `tests/setup.ts`。           |

新业务页面放 `src/pages/`，需要沿用 web_ui 会话/任务布局时放 `src/pages/chat/` 或 `src/pages/schedule/`。基础原语放 `src/components/ui/`，业务组件按模块放 `src/components/<module>/`；组件源码文件用 PascalCase，其余源码文件用 camelCase；组件测试与组件同名（PascalCase），hook/工具测试用 camelCase，且统一放 `tests/` 镜像目录，不与源码同目录。`AGENTS.md` 目前要求页面负责取数、组件只负责展示；现有业务复合组件中的直接取数是待确认的规范与代码差异，不应当在新代码中照搬。路由以 `src/app/App.tsx` 为准。web_ui 已拆入上述目录，来源与许可见 `frontend/UPSTREAM_LICENSE`。
