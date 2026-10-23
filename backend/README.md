# Paper Agent Backend

Paper Agent 的 FastAPI 业务服务负责账号与登录态、个人文献库、项目范围、文献处理任务和混合检索；AgentScope 会话服务与文献解析 worker 分别运行在独立进程；0081 批准独立邮件投递 worker，部署入口已接入启动脚本，功能验收另记。

功能契约见 [../docs/DECISIONS.md](../docs/DECISIONS.md)，包与依赖边界见 [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)，技术选型见 [../docs/research/platform/technical-stack.md](../docs/research/platform/technical-stack.md)。协作约束见仓库根 [AGENTS.md](../AGENTS.md)。

## 本地依赖

- Python 3.13（由 `.python-version` 固定，`uv` 会自动安装）
- PostgreSQL 16 + pgvector、Redis 7（`docker compose up -d postgres redis`，在仓库根目录执行，见 `docker-compose.yml`）

## 启动

```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run python -m app.literature_support.processing.worker  # 另一个终端
uv run python -m app.platform.mail_worker  # 独立邮件终端
```

完整本地服务从仓库根目录运行 `./start.sh`，同时启动业务服务、解析/邮件 worker、AgentScope 会话服务、PostgreSQL、Redis 和前端。脚本等待 Redis PING，任一服务进程退出会停止其他子进程；Ctrl-C 不删除 Compose 容器或数据。

服务启动后可访问：

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

AgentScope Credential 使用独立的 `CREDENTIAL_MASTER_KEY`（32 随机字节的 hex），按用户派生对称密钥加密 API Key。`./start.sh` 仅在 agent_service 数据库尚无凭据时自动生成并写入 `backend/.env`；首次生成后请安全备份。主密钥丢失时已有凭据无法解密，服务会拒绝启动。`CREDENTIAL_BASE_URLS` 可由服务端设置 Provider endpoint 白名单，浏览器提交其他 URL 会被拒绝（见决策 0015）。

## 邮箱认证与任务通知部署

批准契约见 [0081](../docs/decisions/0081-email-auth-and-schedule-notifications.md)。邮件模板可用 `uv run python -m app.platform.mail_preview` 生成到根目录 `.var/mail-previews/index.html`，只使用合成示例且不发送邮件。浏览器闭环验收与实际收件确认单独进行。

配置写入 `backend/.env`，由业务服务、AgentScope 与独立 worker 的 settings 加载；根 `.env` 仅用于 Compose 插值，仍有有效配置，必须保留。下列示例全部留空，不可直接当作可运行配置：

```dotenv
REDIS_URL=
PUBLIC_APP_URL=
SMTP_HOST=
SMTP_PORT=
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_FROM_NAME=
SMTP_USE_SSL=
SMTP_STARTTLS=
```

- 本地 Compose Redis 使用标准 `6379`（容器内与本机映射一致）；本机不得再运行第二个 Redis。`backend/.env` 的 `REDIS_URL` 指向该端口，应用容器部署时使用服务名 `redis:6379`。仅保存验证码、用途绑定的一次性凭证、冷却与限流。默认关闭 RDB/AOF，没有持久卷；可选持久化不改变“状态丢失重新验证”的要求。不可用时不得绕过邮箱校验。
- `PUBLIC_APP_URL` 填浏览器可访问的可信站点根地址；生产使用 HTTPS。通知内运行链接仍需登录并校验归属，不能填 Agent 内部服务地址或以链接代替授权。
- QQ SMTP 的主机为 `smtp.qq.com`；可选择 465 隐式 TLS（开启 `SMTP_USE_SSL`，关闭 `SMTP_STARTTLS`），或服务端支持的 STARTTLS 方案（关闭 SSL、开启 STARTTLS 并使用对应端口），不可同时开启两种模式。`SMTP_USERNAME`/`SMTP_FROM_EMAIL` 使用获授权发信邮箱，`SMTP_PASSWORD` 使用独立 SMTP 授权码而非网页登录密码；`SMTP_FROM_NAME` 为发件人显示名。
- 真实 SMTP 参数只由主 agent 写入未提交的 `backend/.env`，不在终端打印、提交或放入前端配置；配置示例只留空。不要使用会展开真实配置的 `docker compose config` 输出，静态验证使用 `docker compose config --quiet`。
- 邮件由 PostgreSQL 加密 outbox 与 `uv run python -m app.platform.mail_worker` 投递；无需 Celery。正文使用由 `CREDENTIAL_MASTER_KEY` 派生的密钥加密，开发环境未配主密钥时回退到 JWT 密钥；轮换前须先处理待发邮件，不能丢失原密钥。SMTP 暂时错误退避重试，最多 5 次；永久拒绝立即失败，过期验证码不发。`accepted` 只表示 SMTP 接受，不保证进入收件箱；接受后进程中断的极端情况可能重复投递。日志在根 `.var/logs/mail-worker.log`，不得记录验证码、凭据或完整正文。
- 注册与找回各走独立三步：邮箱发送验证码 → 校验取得一次性凭证 → 设置并确认密码。验证码 10 分钟有效、60 秒重发冷却、错误 5 次失效；每邮箱每小时最多发送 5 次、每 IP 每小时 20 次；密码为 8–128 字符并二次确认。重置成功撤销全部登录会话并发送安全邮件；Agent 每个认证请求通过 HTTP 回查业务登录态，旧 token 不再有效。
- 任务通知默认关闭，只发任务所属用户的已验证邮箱；Agent 只传通知布尔值，不传收件地址，也不新增 always-allow。成功发送最终完整 Markdown 回答的安全 HTML/纯文本版及运行链接；失败只发送可行动错误与链接，不发送 partial。公式保留 LaTeX、图片给说明及站内链接；邮件超限须明确提示部分展示，并指向完整站内结果。
- 当前 AgentScope 源码的 `/health` 依赖认证，启动脚本使用进程存活与 TCP 检查；业务服务公开 `/health` 继续用于 HTTP 检查。探针不签发虚假用户 JWT、不绕过生产认证，TCP 就绪不等于业务认证或完整组件健康。
- 旧账号清理尚无执行范围授权，不运行清库、删除对象或 `docker compose down -v`；数据库迁移和部署不构成数据删除授权。

## 测试

集成测试直接连接真实 PostgreSQL（用到 pgvector 与全文检索）：

```bash
docker compose -f ../docker-compose.yml up -d postgres
uv run pytest
```

测试默认使用 `DATABASE_URL` 指向的库，并通过 `TEST_DATABASE_URL` 覆盖。

## 目录结构

```text
app/
├── auth/         # 账号与登录态
├── imports/      # DOI/arXiv 导入、库外文献发现与入库队列
├── processing/   # 处理任务、阶段状态和重试入口
├── library/      # 个人文献库与共享 PDF
├── projects/     # 项目与文献成员
├── retrieval/    # 授权检索与 Chunk 仓储
├── sessions/     # AgentScope 会话绑定与已登记引用
├── literature_support/  # PDF/MinerU、分块、向量、学术来源与证据算法
├── agent/        # LLM 模型目录
├── platform/     # 配置、数据库、日志、错误、存储与调度
└── main.py       # FastAPI 应用装配
alembic/          # 版本化数据库迁移
tests/            # 按职责分包的测试与架构约束
```

有 Router 的业务包统一为 `api.py`、`schemas.py`、`depends.py`、`service.py`、
`domain.py`、`repo.py`、`ports.py`，另有 `__init__.py`。`depends.py` 负责 HTTP 依赖装配，
`service.py` 负责用例，`repo.py` 负责 ORM；复杂执行过程、外部适配器和纯工具放在同级支持包。

## 接口一览

| 领域     | 接口                                                                                     |
| -------- | ---------------------------------------------------------------------------------------- |
| 认证     | `POST /v1/auth/register\|login\|refresh\|logout`、`GET /v1/auth/me`                      |
| 论文库   | `POST/GET /v1/papers`、`GET /v1/papers/{paper_id}`、`GET /v1/papers/{paper_id}/pdf`      |
| 补全文   | `POST /v1/papers/{paper_id}/pdf`、`POST /v1/papers/{paper_id}/fetch-pdf`                 |
| 元数据   | `PATCH /v1/papers/{paper_id}/metadata`、`POST /v1/papers/{paper_id}/resolve-metadata`    |
| 处理任务 | `GET /v1/ingestion-jobs/{job_id}`、`POST /v1/ingestion-jobs/{job_id}/retry`              |
| 项目     | `/v1/projects`、`/v1/projects/{project_id}`、`GET/POST /v1/projects/{project_id}/papers` |
| 会话绑定 | `POST/GET /v1/session-bindings`、`DELETE /v1/session-bindings/{session_id}`              |
| 引用     | `GET /v1/session-bindings/{session_id}/citations/{citation_id}`                          |
| 模型目录 | `GET /v1/llm-catalog`                                                                    |
| 检索     | `POST /v1/search`（library / project / paper 三种授权范围）                              |
| 导入     | `POST /v1/imports`、`GET /v1/imports/{import_id}`                                        |

所有错误统一为 `{"code", "message", "request_id"}`；`code` 是稳定的 snake_case 字符串。上传、消息与重试类操作
都会校验归属，越权访问统一按“不存在”处理。

## Provider 配置说明

MinerU 与 Embedding 都是**远程服务**，本机不再跑任何模型容器；docker compose 只保留
PostgreSQL、Redis 与对象存储。

### MinerU（远程）

使用 MinerU 官方 HTTP API（`/api/v4` 上传地址 → PUT PDF → 轮询批次 → 下载并校验 ZIP）：

```dotenv
MINERU_API_URL=https://mineru.net
MINERU_API_KEY=sk-...
MINERU_TIMEOUT_SECONDS=600
```

`MINERU_API_URL` 只填 base URL；误填到具体端点时适配器会归一化。预签名上传地址**不能**带
`Content-Type`（OSS 按空 Content-Type 签名，否则 403 SignatureDoesNotMatch）。响应由
`code/msg/trace_id/data` 包装，`code != 0` 会映射成稳定错误码。ZIP 仍检查路径穿越、下载
大小与解压后各类产物大小。

### Embedding（远程，SiliconFlow）

**两侧分开计费**：入库时的向量由部署级 Key 产生（chunk 向量是共享资产），检索时的
query 向量用提问者自己的 Key——在设置页「向量检索」里保存。两侧模型必须相同：用户只提供
Key，不能选模型或 Base URL，否则 query 与 chunk 会落在不同向量空间，召回静默失真。
用户没配 Key 时检索只走关键词，向量通道标记为不可用。

```dotenv
EMBEDDING_API_URL=https://api.siliconflow.cn/v1
EMBEDDING_API_KEY=sk-...
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSIONS=1024
```

`BAAI/bge-m3` 是 1024 维、多语言、无需 query/document 前缀，与 `chunks.embedding` 列一致。
批大小与字符上限走 `app/literature_support/embedding/profiles.py` 的档案默认值
（32 条 / 32000 字符），需要时用 `EMBEDDING_MAX_BATCH_ITEMS`、`EMBEDDING_MAX_BATCH_CHARS`
覆盖。`EMBEDDING_TIMEOUT_SECONDS` 是单请求读超时（默认 120 秒），与元数据查询共用的
`OUTBOUND_TIMEOUT_SECONDS` 分开，避免长批量被误判超时。
换模型就换了向量空间，同维度的旧向量也**不能**混用，必须整库重算。

集成测试会在会话内清空 Provider 配置，避免用例依赖本地 `.env`；
确实想用真实服务跑测试时设置 `PAPER_AGENT_LIVE_PROVIDERS=1`。

## 手工验证真实解析

```bash
cd backend
# 用 .env 里配置的远程 MinerU/Embedding 上传一篇真实英文论文，观察阶段与检索
uv run python - <<'SCRIPT'
import time, uuid
from pathlib import Path
import httpx

pdf = Path("/path/to/paper.pdf")
with httpx.Client(base_url="http://127.0.0.1:8000", timeout=120) as c:
    email = f"check-{uuid.uuid4().hex[:6]}@example.com"
    token = c.post("/v1/auth/register", json={"email": email, "password": "check-pass-1"}).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    with pdf.open("rb") as fh:
        job = c.post("/v1/papers", headers=auth, files={"file": (pdf.name, fh, "application/pdf")}).json()
    job_id, paper_id = job["ingestion_job"]["id"], job["paper"]["id"]
    while True:
        detail = c.get(f"/v1/ingestion-jobs/{job_id}", headers=auth).json()
        print({stage["stage"]: stage["status"] for stage in detail["stages"]}, detail["status"])
        if detail["status"] in {"succeeded", "failed"}:
            break
        time.sleep(3)
    print(c.get(f"/v1/papers/{paper_id}", headers=auth).json()["capabilities"])
    print(c.post("/v1/search", headers=auth, json={"query": "your query"}).json()["status"])
SCRIPT
```

## 当前未接入的能力

- AgentScope 执行器：会话、pending 队列、SSE 与引用都已实现，但执行器仍返回 `agent_unavailable`，不会伪造回答；
- MinerU / Embedding：未配置时对应阶段失败并记录 `provider_not_configured`，已完成的阶段能力继续可用；
- 邮件功能按 0081 已批准，业务实现与真实 SMTP 验收另记；Redis 仅承载临时验证状态，邮件 outbox 存 PostgreSQL，解析与邮件各用独立 worker，不引入 Celery。
- MinIO：社区版已停止维护；对象存储改用 RustFS（本地开发/试用）或云对象存储，接口层不变。

## 日志

日志使用 `structlog`，底层统一走标准库 `logging`。默认输出开发态可读文本，`LOG_JSON=true` 输出单行 JSON；每个请求会返回并记录 `X-Request-ID`。禁止记录 Token、Cookie、密码、请求体、文献原文与模型提示词。

## 凭据与端口

- **不入库的凭据**：仓库根 `.env`（compose 用：`POSTGRES_PASSWORD`、`RUSTFS_ACCESS_KEY/SECRET_KEY`）
  与 `backend/.env`（后端用：`DATABASE_URL`、`JWT_SECRET_KEY`、`MINERU_API_URL`、`EMBEDDING_API_URL`、
  `S3_ACCESS_KEY/SECRET_KEY`、Redis/邮件配置与 SMTP 授权码）都在 `.gitignore` 里；邮件配置示例只保留空值，不提交真实秘密。
- **两处密码必须一致**：compose 的 `POSTGRES_PASSWORD` 与 `backend/.env` 里 `DATABASE_URL` 的密码。
  改密码时注意 `POSTGRES_PASSWORD` **只在数据卷首次初始化时生效**，已有数据卷上要用
  `docker exec -it paper-agent-postgres psql -U paper_agent -d postgres -c "ALTER USER paper_agent WITH PASSWORD '新密码';"`
  （`docker compose down -v` 会重建数据卷，数据全部丢失）。
- **`JWT_SECRET_KEY` 必须是随机值**：`openssl rand -hex 32`，只写进 `backend/.env`。
  占位符、短于 32 字符或低熵的密钥会在启动时报 `configuration.weak_jwt_secret`，
  且 `ENVIRONMENT` 非 `development` 时直接拒绝启动。
- **端口只绑本机**：Postgres 5432、Redis 6379、TEI 8080、RustFS 9000/9001 都是 `127.0.0.1:`；对外只暴露后端与前端。

## 对象存储

PDF、MinerU 产物与会话 Entry 日志都通过 `app/platform/storage.py` 的 `ObjectStorage`
接口读写，两种实现按 `STORAGE_BACKEND` 选择：

| 后端                | 适用                               | 配置                                                                |
| ------------------- | ---------------------------------- | ------------------------------------------------------------------- |
| `local`（开发默认） | 仅开发与测试；`local_path` 零拷贝  | `STORAGE_ROOT`（默认 `.var/storage`）                               |
| `s3`（生产必选）    | 自建或云对象存储，启动时检查可用性 | `S3_ENDPOINT_URL` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_BUCKET` |

- 自建对象存储用 **RustFS**（Apache-2.0，S3 兼容）：`docker compose --profile storage up -d storage`，
  控制台在 `http://127.0.0.1:9001`。RustFS 官方标注处于快速开发阶段，**不要用于生产**；
  生产应使用经过验证的 S3 兼容服务或云对象存储。
- 换后端是配置变更：Key 布局（`papers/…`、`mineru/…`、`sessions/…`）不变，业务代码不感知。
- 唯一差异由 `materialize()` 抹平：MinerU 上传需要真实文件路径，`s3` 实现会下载到临时文件并在退出时删除。
- 一致性由 `tests/platform/test_object_storage.py` 保证：同一组用例跑在 local、模拟 S3 与
  （`PAPER_AGENT_LIVE_STORAGE=1` 时的）真实服务上。

## Agent 执行

Agent 回合由独立的 `agent_service` 使用 AgentScope 执行。业务服务的 `GET /v1/llm-catalog`
从 AgentScope Model Card 返回可选 Provider 与 active 模型；会话配置引用用户的 Credential，
不携带明文 API Key。`PaperAgent` 固定装配以下工具组，运行中不切换工具列表：

| 工具组         | 工具                                                | 作用                                               |
| -------------- | --------------------------------------------------- | -------------------------------------------------- |
| 文献阅读       | `list_papers`、`search_papers` | 列出授权文献、检索并登记证据 |
| 库外发现与入库 | `discover_papers`、`import_selected_papers`         | 查找库外候选；经用户授权后入库                     |
| 用户交互       | `ask_user`                                          | 暂停回复并收集用户答案                             |
| 系统功能       | `create_scheduled_task`                             | 经用户授权后创建定时任务                           |

- 文献与项目范围由服务端按会话绑定注入，**不由模型参数决定**；只有已登记的证据才能引用。
- 入库与创建定时任务默认逐次请求用户授权，明确配置为总是允许时才跳过审查。
- 会话消息和工具结果由 AgentScope 持久化；业务服务只通过 `session_id` 关联会话与已登记引用。
- Provider 与模型只能从服务端目录选择；Base URL 受服务端白名单约束。

## 数据流向

为了产出可用回答，系统会把数据发给外部服务：

- PDF 发往 MinerU 解析正文；
- Chunk 文本发往 Embedding 服务生成向量；
- 用户问题与检索到的论文证据发往用户选择的 LLM Provider；
- 按 0081，验证码和安全通知通过部署者的 SMTP 服务发送；用户显式开启任务通知后，最终回答或可行动失败信息也会经 SMTP 发往本人已验证邮箱。

LLM API Key 由 AgentScope Credential 存储适配层加密后保存在会话服务数据库中；浏览器只在创建或更新凭据时提交 Key，列表与更新响应不回传明文。Key 不进入日志、对象存储或任务队列。MinerU 与 Embedding 仍由部署者通过环境变量固定。
