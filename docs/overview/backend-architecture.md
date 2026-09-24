# 后端源码架构

本说明对应 2026-09-24 的后端模块整理。描述当前源码组织，不扩展 MVP 范围。
功能契约见 [minimal-mvp.md](minimal-mvp.md)，术语见 [CONTEXT.md](../../CONTEXT.md)。

## 1. Router 业务包

`auth`、`imports`、`ingestion`、`library`、`projects`、`retrieval`、`sessions` 均使用以下结构；
除 Python 包入口 `__init__.py` 外，不放其他源文件或实现子包。

| 文件 | 职责 |
|---|---|
| `api.py` | HTTP 路由、认证依赖、调用服务、响应转换；不直接查询仓储 |
| `schemas.py` | Pydantic 请求/响应模型与接口数据转换 |
| `depends.py` | FastAPI 依赖装配，从请求和应用状态取得所需对象 |
| `service.py` | 用例编排、资源归属检查、事务协调 |
| `domain.py` | 领域对象、枚举、局部业务规则 |
| `repo.py` | SQLAlchemy 表、查询和持久化操作 |
| `ports.py` | 本包使用的外部能力契约，不放空占位或具体适配器 |

这是模块化单体。服务仍可使用本包及其他业务包的具体仓储，并未引入一套完整的仓储抽象或 Unit of Work。
已有的 HTTP 路径、请求响应、数据库表、对象存储 Key 和业务行为保持原样。

## 2. 同级支持包

| 包 | 文件和职责 | 主要使用方 |
|---|---|---|
| `processing` | `service.py`：处理流水线及共享装配函数；`mineru.py`：解析服务适配；`chunks.py`：分块；`pdf.py`：PDF 校验；`text.py`：前页文本与标识符提取 | ingestion、library、imports、agent |
| `embedding` | `base.py`：模型档案类型和输入准备；`profiles.py`：模型默认参数；`client.py`：兼容 Embeddings API 的实现；`__init__.py`：适配器工厂 | retrieval、processing |
| `agent` | `service.py`：SessionExecutor；`scope.py`：AgentScope 适配；`catalog.py`：模型目录与配置校验；`tools.py`：只读文献工具；`fallback.py`：未配置执行器的失败实现 | sessions、应用启动 |
| `conversation` | `service.py`：EntryStore JSONL 历史；`context.py`：历史消息投影；`events.py`：内存 EventBroker | sessions、agent |
| `evidence` | `ranking.py`：RRF、证据配额与相邻合并；`citations.py`：稳定引用 ID | retrieval、sessions |
| `scholar` | `identifiers.py`：标识符解析；`metadata.py`：元数据查询；`merge.py`：字段合并规则；`pdf_fetch.py`：全文下载 | library、imports、processing |
| `platform` | 配置、数据库、存储、调度、日志、错误、安全和分页等共享技术设施 | 全部业务包 |

纯计算和输入转换保留为函数；有运行状态或外部交互的能力使用现有类。不为凑统一外观给支持包增加 Router、repo 或无意义的转发类。

## 3. ports 的实际用途

| 业务包 | 接口 |
|---|---|
| auth | `AuthStore`：认证服务需要的账户与令牌存取，由 `AuthRepository` 满足 |
| imports | `IngestionStarterFactory`：导入取得 PDF 后创建处理服务的工厂，明确输入和返回类型 |
| ingestion | `IngestionJobRunner`：执行已创建任务，由 `IngestionPipeline` 满足 |
| library | `IngestionStarter`：文献库需要的处理任务创建、查询和重试能力 |
| projects | `ProjectSessionCleaner`：项目删除时的关联会话清理能力 |
| retrieval | `EmbeddingAdapter`：检索和索引所需的向量生成能力，由 embedding 包实现 |
| sessions | `AgentRunner`、回合输入、事件和临时 LLM 配置：应用与执行框架之间的契约 |

## 4. 依赖与装配

正常请求经过 `api → service → repo/外部能力`。`schemas` 处理输入输出，`depends` 负责 HTTP 装配。

- Router 不直接导入 repo 或 SQLAlchemy；例如处理任务的用户条目归属检查在 `IngestionService` 中完成。
- service、domain、repo、ports 和支持实现不直接导入 FastAPI，也不反向导入 api、schemas、depends。
  platform 中现有的共享设施仍包含 FastAPI 依赖提供函数；上述规则不声称完全消除了框架的间接依赖。
- `processing.service.build_ingestion_service` 是请求、导入和工具共用的装配入口，使用普通参数而非 FastAPI Depends 注解。
  它连接任务管理与执行流水线，执行代码无需反向导入 `ingestion.depends`。
- `app/main.py` 装配进程级调度器、EventBroker、SessionExecutor；业务 `depends.py` 从 `app.state` 取得这些对象。
- `app/models.py` 导入各业务 repo，确保 ORM 表注册到共享 `Base.metadata`；Alembic 继续通过它加载表。

支持包之间按需要引用领域契约。比如 processing 更新 ingestion 的任务状态及 retrieval 的 Chunk，
agent 使用 sessions 的回合契约和业务服务；这些是单体内明确的协作关系，不表示已经拆成可独立部署的服务。

## 5. 主要执行路径

```text
上传：library.api → library.service → ingestion 服务契约
      → ingestion.service → processing.service
      → 元数据 / MinerU / chunks / embedding

导入：imports.api → imports.service → scholar
      → library.service 绑定 PDF → 共用处理流水线

问答：sessions.api → sessions.service → agent.service
      → conversation 历史与上下文 → agent.scope → agent.tools
      → library / retrieval / 引用登记
      → conversation 历史落盘与实时事件
```

会话元数据、pending 和引用在 PostgreSQL；Entry 在本地/S3 对象存储；实时事件缓冲和活动执行状态在进程内。
此次调整不引入 Redis、Celery、多进程协调或新的恢复机制。

## 6. 旧路径迁移

- 所有业务包：`dependencies → depends`、`application → service`、`persistence → repo`。
- `library/pdf.py`、`text_extraction.py` → `processing/pdf.py`、`text.py`。
- `library/metadata_merge.py` → `scholar/merge.py`。
- `ingestion/pipeline.py`、`mineru.py`、`chunking.py` → `processing/service.py`、`mineru.py`、`chunks.py`。
- `retrieval/embedding/` → `embedding/`；`openai_compatible.py` → `client.py`；接口定义迁至 `retrieval/ports.py`。
- `retrieval/fusion.py` → `evidence/ranking.py`；`sessions/citations.py` → `evidence/citations.py`。
- `sessions/executor.py`、`agent_scope.py`、`model_catalog.py`、`tools.py` → agent 包。
- `sessions/agent.py` 中的执行契约 → `sessions/ports.py`；校验和未配置实现 → agent 包。
- `sessions/entries.py`、`events.py`、`context.py` → conversation 包。

旧导入路径不保留兼容壳；代码、测试和入口统一引用新路径。相应支持实现的测试也迁到同名测试包。

`tests/test_architecture.py` 检查业务包文件结构、执行代码不反向引用 HTTP 装配，以及 Router 不直连仓储。
行为回归继续使用现有 PostgreSQL 测试；重构验收还需核对 OpenAPI 未发生变化。
