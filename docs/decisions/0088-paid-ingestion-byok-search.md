# 0088 — 入库由平台付费，检索用用户自己的 Key

- DATE: 2026-10-24
- TAGS: retrieval, security, ingest
- STATUS: 当前
- SUPERSEDES: 0087 中「检索也用部署级 Key」的片段

## DECISION

- 入库向量化用部署级 `EMBEDDING_API_KEY`：入库是低频、大批量操作，且产出的 chunk 向量由所有用户共享，cost 归平台才能让权责一致。
- 检索的 query 向量用**发起提问的那个用户**自己的 Key，存进 `service_credentials`（`kind="embedding"`，只有 `api_key` 一个加密字段）。检索频次因人而异，额度和速率限制由使用者自负。
- 两侧模型由部署决定且必须相同（当前 SiliconFlow `BAAI/bge-m3`，1024 维）。用户只提供 Key，不选模型、不填 Base URL：query 与 chunk 若来自不同模型，维度可能相同而向量空间不同，余弦距离会静默失真。
- 用户未配置 Key 时，检索照常返回关键词结果；向量通道 `status=unavailable`、`detail="no embedding api key"`，整体 `degraded`。不抛错，也不回退到平台 Key。
- 用户在检索时 Key 失效（401/429/超时）与未配置的处理相同：向量通道不可用，只有关键词召回。
- 检索侧的适配器工厂是 `get_search_embedding_factory`，按 `user_id` 现取现建；`SearchService` 只接受工厂，不再持有全局适配器。入库路径完全不看用户凭据。
- 设置页新增 `/settings/retrieval`（向量检索），只负责保存/移除这把 Key；失败文案沿用 0032，不自拟错误分类。

## REJECTED

- 检索也用平台 Key：检索是高频操作，用户越多平台成本越不可控，且无法解释「谁消耗了额度」。
- 允许用户选模型或填 Base URL：会破坏「query 与 chunk 同模型」这一前提，产生不可见的召回退化。
- 没配 Key 直接报错：会让人误以为检索功能坏掉；关键词召回本来就是有效的降级。
- 入库也按用户 Key 计费：共享文献的向量谁先入库谁付费，权责不清（见 0086）。

## OUT OF SCOPE

用量统计与计费报表、按用户的额度上限、多模型共存、rerank。

## OPEN

- 用户 Key 泄露或被盗用无法追溯（只记录失败类型，不记录 Key）。
- 若将来部署侧换模型，所有用户的 query 向量需随 chunk 向量一起重建。
