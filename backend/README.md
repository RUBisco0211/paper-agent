# Paper Agent Backend

Paper Agent 的 FastAPI 业务服务负责账号与登录态、个人文献库、项目范围、文献处理任务和混合检索；AgentScope 会话服务与文献解析 worker 分别运行在独立进程。

功能契约见 [../docs/DECISIONS.md](../docs/DECISIONS.md)，包与依赖边界见 [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)，技术选型见 [../docs/research/platform/technical-stack.md](../docs/research/platform/technical-stack.md)。协作约束见仓库根 [AGENTS.md](../AGENTS.md)。

## 本地依赖

- Python 3.13（由 `.python-version` 固定，`uv` 会自动安装）
- PostgreSQL 16 + pgvector（`docker compose up -d postgres`，见仓库根目录 `docker-compose.yml`）

## 启动

```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run python -m app.literature_support.processing.worker  # 另一个终端
```

完整本地服务从仓库根目录运行 `./start.sh`，同时启动业务服务、解析 worker、AgentScope 会话服务、PostgreSQL 和前端。

服务启动后可访问：

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

AgentScope Credential 使用独立的 `CREDENTIAL_MASTER_KEY`（32 随机字节的 hex），按用户派生对称密钥加密 API Key。`./start.sh` 仅在 agent_service 数据库尚无凭据时自动生成并写入 `backend/.env`；首次生成后请安全备份。主密钥丢失时已有凭据无法解密，服务会拒绝启动。`CREDENTIAL_BASE_URLS` 可由服务端设置 Provider endpoint 白名单，浏览器提交其他 URL 会被拒绝（见决策 0015）。

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

| 领域 | 接口 |
|---|---|
| 认证 | `POST /v1/auth/register\|login\|refresh\|logout`、`GET /v1/auth/me` |
| 论文库 | `POST/GET /v1/papers`、`GET /v1/papers/{paper_id}`、`GET /v1/papers/{paper_id}/pdf` |
| 补全文 | `POST /v1/papers/{paper_id}/pdf`、`POST /v1/papers/{paper_id}/fetch-pdf` |
| 元数据 | `PATCH /v1/papers/{paper_id}/metadata`、`POST /v1/papers/{paper_id}/resolve-metadata` |
| 处理任务 | `GET /v1/ingestion-jobs/{job_id}`、`POST /v1/ingestion-jobs/{job_id}/retry` |
| 项目 | `/v1/projects`、`/v1/projects/{project_id}`、`GET/POST /v1/projects/{project_id}/papers` |
| 会话绑定 | `POST/GET /v1/session-bindings`、`DELETE /v1/session-bindings/{session_id}` |
| 引用 | `GET /v1/session-bindings/{session_id}/citations/{citation_id}` |
| 模型目录 | `GET /v1/llm-catalog` |
| 检索 | `POST /v1/search`（library / project / paper 三种授权范围） |
| 导入 | `POST /v1/imports`、`GET /v1/imports/{import_id}` |

所有错误统一为 `{"code", "message", "request_id"}`；`code` 是稳定的 snake_case 字符串。上传、消息与重试类操作
都会校验归属，越权访问统一按“不存在”处理。

## Provider 配置说明

`MINERU_API_URL` 只填 **base URL**（例如 `https://mineru.net`）：适配器会自行拼接
`/api/v4/file-urls/batch`（申请上传地址）与 `/api/v4/extract-results/batch/{batch_id}`（轮询结果）。
即使误填了具体端点（例如 `https://mineru.net/api/v4/extract/task`），适配器也会归一化到 base URL；
只有自建服务挂在子路径下（不含 `/api/v4`）时才原样使用。

适配器已经处理的两个 MinerU 实际行为（都有回归用例）：

1. **预签名上传地址不能带 `Content-Type`**：OSS 签名按空 Content-Type 计算，多带一个头会返回
   `403 SignatureDoesNotMatch`。
2. 响应由 `code/msg/trace_id/data` 包装：`code != 0` 时把 `msg` 映射成稳定错误码（鉴权 →
   `provider_not_configured`、限流 → `provider_rate_limited`、其他 → `provider_unavailable`）；
   `waiting-file` 持续过久会明确报"未收到上传的文件"。

用测试时不需要这些凭据：集成测试会在会话内清空 Provider 配置，避免用例依赖本地 `.env`；
确实想用真实服务跑测试时设置 `PAPER_AGENT_LIVE_PROVIDERS=1`。

## Embedding（可选）

向量通道由一个 **OpenAI 兼容的 `/embeddings`** 服务提供，默认按 `BAAI/bge-m3` 配置
（1024 维 / 8192 上下文 / 不需要 query、document 前缀，适合英文论文长句）。
推荐 `text-embeddings-inference`（TEI）：本地与服务器同一套接口，只是镜像/安装方式不同。

### 云服务（本地开发推荐）

本地不需要跑模型，把 `.env` 指向云即可（与自建走同一套适配器）：

```dotenv
# 阿里云百炼 DashScope（当前默认）：text-embedding-v3，1024 维
EMBEDDING_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_DIMENSIONS=1024
```

供应商差异都在模型档案里：DashScope 单请求 **≤10 条**且整批 token 有上限，适配层会同时按
「条数」和「总字符」拆包；SiliconFlow 提供同款 `BAAI/bge-m3`（1024 维，32 条/请求），
复用同一份档案。两者维度都是 1024，与迁移一致，**不需要迁移**。

### 自建（服务器）

Docker 是唯一入口（本地与服务器同一套）：

```bash
cd <仓库根>

# 只跑数据库（日常开发，不起模型）
docker compose up -d postgres

# 本地联调：数据库 + Embedding（首次会拉镜像约 1.5GB、模型约 2.3GB）
./start.sh --with-embeddings

# 服务器：把 TEI_IMAGE 换成匹配 GPU 的镜像后整体拉起
TEI_IMAGE=ghcr.io/huggingface/text-embeddings-inference:1.9 docker compose up -d
```

### 权重来源（两条路）

1. **容器内下载**（服务器默认）：`EMBEDDING_MODEL=BAAI/bge-m3`，权重缓存在 `embedding-data`
   卷里。需要容器能访问 HuggingFace；容器**不会**继承宿主机代理，网络受限时可在仓库根 `.env`
   设 `HF_ENDPOINT` 指向镜像。
2. **宿主机预下载 + 挂载**（无法直连 HF、或镜像源缺 etag 时用这条）：

   ```bash
   cd <仓库根>
   ./scripts/fetch-embedding-model.sh        # 默认从 ModelScope 取 BAAI/bge-m3 的 dense 权重
   # 仓库根 .env
   EMBEDDING_MODEL=/models/bge-m3
   docker compose up -d embedding
   ```

   该脚本只取 dense 推理需要的文件（不含 `onnx/`、`colbert_linear.pt`、`sparse_linear.pt`，
   省掉约 2GB），`./models` 以只读方式挂到容器 `/models`。

  实测结论（脚本已按此实现）：

   - **ModelScope 支持 Range 分片**：10 连接并行约 4~5MB/s，是受限网络下的首选源
     （`SOURCE=modelscope`，默认）。国内直连可达，无需代理。
   - **hf-mirror 的大文件走 Xet 重建、不支持 Range**，单连接速率在 0.1~1.3MB/s 之间波动，
     只能用单连接兜底（`SOURCE=hf-mirror`）。
   - 宿主机若配置了 HTTP 代理，`curl`/`hf` 默认走代理，而代理在 GB 级传输上会中途卡死
     （下载停在某个字节不再增长）。脚本对下载源设了 `--noproxy '*'`。
   - `hf download` 的 `--include` 只接受单个模式，多写会被当成显式文件名
     （给出 "Ignoring `--include`" 警告），所以脚本用 curl + 文件列表。
   - 大文件按分片下载后逐片校验大小再拼接，避免服务端忽略 Range 造成错位。

服务器注意：TEI 自身没有鉴权，compose 里只把端口绑到 `127.0.0.1:8080`，不要对外暴露；
模型权重持久化在 `embedding-data` 卷里，重启不会重复下载。
镜像后缀按计算能力选：A100/A30→无后缀、A10/A40→`86-`、RTX 4000→`89-`、H100→`hopper-`、
纯 CPU（x86）→`cpu-`、Apple Silicon→`cpu-arm64-`（版本号 1.9）。

对应配置（`backend/.env`）：

```dotenv
EMBEDDING_API_URL=http://127.0.0.1:8080/v1
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSIONS=1024
```

### 适配层

向量差异都收敛在 `app/literature_support/embedding/`：

```text
base.py              EmbeddingProfile（维度/截断/前缀）+ prepare()
profiles.py          已知模型的默认行为（bge-m3、bge-*-en-v1.5、e5、nomic、embeddinggemma、
                     qwen3-embedding、text-embedding-3-*）；未知模型走默认档案
client.py            实现协议：组装 /embeddings 请求、解析响应、映射错误码
__init__.py          build_embedding_adapter()：按配置装配当前兼容实现
```

协议定义在 `app/retrieval/ports.py`。上层只调用 `embed_documents()`（chunk）与 `embed_query()`（查询），前缀与截断由档案决定，
因此**换模型只需要改配置**；换成非 OpenAI 兼容的服务时，新增一个实现 `EmbeddingAdapter`
的类并在 `build_embedding_adapter()` 里注册即可，检索与流水线代码不用动。

### 换模型

1. 改 `EMBEDDING_MODEL`（模型档案会自动带上维度、截断长度与前缀；除非要覆盖）
2. 维度变了就做一次离线迁移：改 `alembic/versions/*_resize_chunk_embeddings_for_bge.py`
   里的 `NEW_DIMENSIONS` → 新增一次迁移（重建列并重置 `papers.has_embedding`）
3. 对受影响的条目重试处理，重新生成向量（`papers.has_embedding=false` 的条目会被重跑）

启动时会比对 `EMBEDDING_DIMENSIONS` 与 `chunks.embedding` 的实际维度，不一致会记录
`configuration.embedding_dimension_mismatch` 错误日志（而不是等到写入时才发现）。

### 本机实测的容量提醒

fp32 `bge-m3` 权重 2.3GB，加载后常驻约 2.5~3GB。在一台已用 18.8GB swap 的笔记本上强启，
OrbStack 与 Docker 守护进程会一起被换页拖死（`docker ps` 无响应）。因此：

- 本地开发优先用云 Embedding（上面的 DashScope / SiliconFlow），零内存占用；
- 自建留给内存充足的服务器，并用 `--profile embeddings` 显式启用；
- 服务器上按 GPU 选镜像（`TEI_IMAGE`），CPU 上跑 bge-m3 会比较慢。

注意事项：

- **维度必须与迁移一致**：`chunks.embedding` 是 `vector(1024)`（迁移 `20260917_0007`）。
  换模型且维度不同时，需要一次离线迁移：改迁移里的维度 → 重建列 → 迁移会重置
  `papers.has_embedding`，之后对条目重试处理即可重新生成向量。
- **模型名要跟着一起改**：`EMBEDDING_MODEL` 会写进 `chunks.embedding_model`，向量检索按它过滤，
  避免新旧模型向量混用。
- 未配置时 embedding 阶段会以 `provider_not_configured` 失败，全文与关键词检索照常可用（检索状态为 `degraded`）。
- 需要前缀的模型（`e5`、`nomic-embed-text`、`embeddinggemma`）当前不支持：适配层对 query 与 chunk
  使用同一套文本，不注入 `query:`/`passage:` 前缀。

## 手工验证真实解析

```bash
cd backend
# 用 .env 里的 MinerU 凭据上传一篇真实英文论文，观察阶段与检索
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
- Redis / Celery：后台任务在进程内执行，适合单机单进程。
- MinIO：社区版已停止维护；对象存储改用 RustFS（本地开发/试用）或云对象存储，接口层不变。

## 日志

日志使用 `structlog`，底层统一走标准库 `logging`。默认输出开发态可读文本，`LOG_JSON=true` 输出单行 JSON；每个请求会返回并记录 `X-Request-ID`。禁止记录 Token、Cookie、密码、请求体、文献原文与模型提示词。

## 凭据与端口

- **不入库的凭据**：仓库根 `.env`（compose 用：`POSTGRES_PASSWORD`、`RUSTFS_ACCESS_KEY/SECRET_KEY`）
  与 `backend/.env`（后端用：`DATABASE_URL`、`JWT_SECRET_KEY`、`MINERU_API_KEY`、`EMBEDDING_API_KEY`、
  `S3_ACCESS_KEY/SECRET_KEY`）都在 `.gitignore` 里；提交进仓库的只有占位符。
- **两处密码必须一致**：compose 的 `POSTGRES_PASSWORD` 与 `backend/.env` 里 `DATABASE_URL` 的密码。
  改密码时注意 `POSTGRES_PASSWORD` **只在数据卷首次初始化时生效**，已有数据卷上要用
  `docker exec -it paper-agent-postgres psql -U paper_agent -d postgres -c "ALTER USER paper_agent WITH PASSWORD '新密码';"`
  （`docker compose down -v` 会重建数据卷，数据全部丢失）。
- **`JWT_SECRET_KEY` 必须是随机值**：`openssl rand -hex 32`，只写进 `backend/.env`。
  占位符、短于 32 字符或低熵的密钥会在启动时报 `configuration.weak_jwt_secret`，
  且 `ENVIRONMENT` 非 `development` 时直接拒绝启动。
- **端口只绑本机**：Postgres 5432、TEI 8080、RustFS 9000/9001 都是 `127.0.0.1:`；对外只暴露后端与前端。

## 对象存储

PDF、MinerU 产物与会话 Entry 日志都通过 `app/platform/storage.py` 的 `ObjectStorage`
接口读写，两种实现按 `STORAGE_BACKEND` 选择：

| 后端 | 适用 | 配置 |
|---|---|---|
| `local`（开发默认） | 仅开发与测试；`local_path` 零拷贝 | `STORAGE_ROOT`（默认 `.var/storage`） |
| `s3`（生产必选） | 自建或云对象存储，启动时检查可用性 | `S3_ENDPOINT_URL` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_BUCKET` |

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

| 工具组 | 工具 | 作用 |
|---|---|---|
| 文献阅读 | `list_papers`、`search_papers`、`get_paper_excerpt` | 列出授权文献、检索并登记证据、按已登记引用读取原文 |
| 库外发现与入库 | `discover_papers`、`import_selected_papers` | 查找库外候选；经用户授权后入库 |
| 用户交互 | `ask_user` | 暂停回复并收集用户答案 |
| 系统功能 | `create_scheduled_task` | 经用户授权后创建定时任务 |

- 文献与项目范围由服务端按会话绑定注入，**不由模型参数决定**；只有已登记的证据才能引用。
- 入库与创建定时任务默认逐次请求用户授权，明确配置为总是允许时才跳过审查。
- 会话消息和工具结果由 AgentScope 持久化；业务服务只通过 `session_id` 关联会话与已登记引用。
- Provider 与模型只能从服务端目录选择；Base URL 受服务端白名单约束。

## 数据流向

为了产出可用回答，系统会把数据发给外部服务：

- PDF 发往 MinerU 解析正文；
- Chunk 文本发往 Embedding 服务生成向量；
- 用户问题与检索到的论文证据发往用户选择的 LLM Provider。

LLM API Key 由 AgentScope Credential 存储适配层加密后保存在会话服务数据库中；浏览器只在创建或更新凭据时提交 Key，列表与更新响应不回传明文。Key 不进入日志、对象存储或任务队列。MinerU 与 Embedding 仍由部署者通过环境变量固定。
