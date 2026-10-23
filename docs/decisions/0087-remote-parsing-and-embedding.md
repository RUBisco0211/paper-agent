# 0087 — 解析与向量化都改用远程服务

- DATE: 2026-10-24
- TAGS: ingest, deployment, retrieval
- STATUS: 当前
- SUPERSEDES: 0086 的自部署向量化部分；0056 中否决外部解析服务的片段

## DECISION

- MinerU 使用官方远程 API（`/api/v4`：申请上传地址 → PUT PDF → 轮询批次 → 下载校验 ZIP），保留 `MINERU_API_KEY`，单次解析超时 600 秒。预签名上传地址不得带 `Content-Type`。
- Embedding 使用硅基流动的 `BAAI/bge-m3`（OpenAI 兼容 `/v1/embeddings`，1024 维，多语言，无需 query/document 前缀）。`chunks.embedding` 保持 1024 维，无需迁移。
- 本机不再运行任何模型容器：`docker-compose.yml` 只保留 PostgreSQL、Redis 与对象存储；`./start.sh` 去掉 `--with-embeddings` / `--with-mineru`；镜像预下载脚本与其缓存目录一并删除。
- 向量化仍由平台统一产生并共享，用户不提供 embedding 密钥；`build_embedding_adapter()` 使用部署级 `EMBEDDING_API_KEY`，自建服务留空即不发送鉴权头。
- 批大小与字符上限由模型档案决定（bge-m3：32 条 / 32000 字符）；`EMBEDDING_TIMEOUT_SECONDS` 是 embedding 专用读超时（默认 120 秒），与元数据查询共用的 `OUTBOUND_TIMEOUT_SECONDS` 解耦。
- Embedding 对 429 与暂时性 5xx 做有界指数退避重试；失败细节（上游状态码、模型、期望/实际维度）写入阶段失败日志。
- bge-m3 支持中文，检索工具不再要求把查询翻译成英文。
- 换模型即换向量空间：本次清空 `chunks`（94 行）并把 `papers.has_keyword_index / has_embedding` 复位，`session_bound_citations` 与 AgentScope 会话表未动。

## REJECTED

- 本机 Docker 跑 MinerU（3.2.1 CPU pipeline）：实测 8 核负载 13+，与 embedding 抢 CPU，解析明显慢于云端。
- 本机 TEI 跑 bge-large / bge-m3：CPU 推理 45 个 chunk 需 271 秒，且旧批量 32 条 + 20 秒超时必定失败。
- 为省显存改用 `bge-base`（768 维）：要改向量列，且纯英文；跨模型向量不可比。
- 保留自建与远程两套分支：只会让配置与文档长期不同步。

## OUT OF SCOPE

GPU 自建部署、多解析器回退、rerank、中文论文质量调优。

## OPEN

- 远程服务依赖外网与额度；SiliconFlow 的 `BAAI/bge-m3` 当前免费，价格与限流可能变化。
- 库内论文需要重新入库以生成 bge-m3 向量后才恢复向量召回。
