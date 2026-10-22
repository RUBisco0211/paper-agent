# 0083 — 联网搜索与网页读取

- DATE: 2026-10-22
- TAGS: agent, product, security, frontend, data
- STATUS: 当前
- SUPERSEDES: —

## DECISION

- 三个读工具 `web_search` / `web_fetch` / `web_extract_excerpt`，均为 `PaperReadTool`，常驻 toolkit，不弹确认。
- 供应商只接 Tavily：`/search` 与 `/extract` 同一个 Key。`web_fetch` 用 `extract_depth=basic` 返回整页 markdown；`web_extract_excerpt` 传 `query` + `chunks_per_source`（1–5，默认 3）返回按问题挑出的段落。
- `web_fetch` 参数只有 `url / offset / max_chars`，返回 `{content, truncated, next_offset, total_chars, offset_out_of_range}`。`offset_out_of_range: true` 表示 offset 算错了或已读到末尾，**不等于页面读完**，agent 应回到 0 起重读；工具描述里写明这一点，不让模型自己算 offset。`max_chars` 上限 20000；`web_extract_excerpt` 参数是 `url / query / chunks`，返回 `excerpt_only: true`。两个工具的参数空间各自自洽，不出现"某参数只在某个分支下有效"的形状，也不靠返回值字段掩盖两种读法的差异。
- 摘录工具是独立工具而非 `web_fetch` 的可选 `query` 参数：可选参数会让 `offset / max_chars` 在 `query` 存在时失去意义，模型能从参数名反推出实现取舍。
- 网页内容**不作为 Citation 来源**：不登记证据、不产出 `citation_id`、不新增网页来源类型。前端只做工具结果展示与点击跳转。
- 全文读取缓存进 Redis：key `web_page:{user_id}:{sha256(url)}`，value 是 Tavily 原始 `raw_content`，TTL 1 小时，翻页在本地切片。只缓存整页读取；摘录读取不缓存，重复读取接受重复计费。Redis 不可用降级为不缓存并直接出网。
- `raw_content` 原样透传：不解析 HTML、不抽取结构化字段、不从正文推断标题。Tavily 的 `title` 字段本就不在 extract 响应里，也刻意不去补。前端结果列表以域名充当条目标题。
- 每用户自带 Key，存进新建的通用服务凭据表 `service_credentials(user_id, kind, label, fields JSONB)`，同 `user_id + kind` 唯一，写入即覆盖。`fields` 中只有 `api_key` 加密（AESGCM，密钥由主密钥 + user_id 经 HKDF 派生），其余字段明文。秘密字段清单由 `spec dict` 声明，新增服务只加一行。
- 工具层不抛异常：`business_request` 把非 2xx 折成 `BusinessRequestFailed`，三个工具统一返回 `{status: "error", code, message, tool}`，前端 renderer 与 agent 读同一个信封。失败码为 `provider_not_configured` / `provider_quota_exhausted` / `rate_limited` / `provider_unavailable`。
- 错误只用一个码族：`provider_not_configured`（该用户没有 Key）、`provider_quota_exhausted`（Tavily 432/433）、`rate_limited`（429）、`provider_unavailable`（401 以外的一切失败：超时、5xx、页面抓不下来）。每个码配一句可行动提示，让人与 agent 都能看懂下一步该做什么。Key 被拒（401）也算 `provider_not_configured`，因为对用户而言要做的动作相同：重填密钥。
- 401 不在库里标记"凭据已失效"：用户可能刚轮换 Key，下次调用自然恢复；持久状态字段会与设置页的"已保存"自相矛盾。
- 供应商未预期的异常（解密失败、报文结构变化）不伪装成上游抖动，也不冒成 500：记 `web.unexpected_provider_error` 日志（含异常类型名），对外仍返回 `provider_unavailable` 并把类型名放进 `details.error`。
- `web_search` 的 `query` 上限 1500 字符，贴合 Tavily 的接受上限；`results` 缺失（而非空数组）按 `provider_unavailable` 处理，不让 agent 误判成"网上没有"。
- 工具实现在 `agent_service/tools/web.py`，只经 `business_request` 调业务服务的 `/v1/internal/web-*`；业务侧在 `app/web/`（api/depends/domain/ports/schemas/service + `page_cache.py`）实现，Tavily 的报文格式封在 `ports.py`。
- `app/web/` 与 `app/service_credentials/` 不套用业务包七文件约束：`tests/test_architecture.py` 改为按显式 `ROUTER_PACKAGES` 清单检查，文件名按内容取（`page_cache.py`、`crypto.py`），不为凑格式改名。
- Redis 客户端改为进程级单例（`app/platform/redis.py`），`app/auth/depends.py` 一并改用它，不再每请求新建连接。
- 设置页拆为左侧分类导航：`/settings/models` 与 `/settings/web-search`，旧的 `/settings` 重定向到模型页。

## REJECTED

- 用 MCP 动态挂载供应商的官方 MCP server：工具名与 schema 不受控，绕开 `PaperAgent` 的 isinstance 白名单；官方适配优势在"不缓存、不引用"的定位下也不成立。
- 用 OpenAI / Anthropic 原生 `web_search`：AgentScope 2.0.6 的模型层只接受函数调用格式，服务端工具跑不通。
- 无 Key 的免费搜索路径（DuckDuckGo 抓取、SearXNG）：没有摘要，对"简称 → 论文实体"没有价值。
- 大陆直连供应商（智谱、博查、阿里 IQS）：只给摘要不给整页正文；IQS 鉴权是阿里云 AK，无法让用户自持可分发的 Key。
- 用一个工具带可选 `query` 同时表达两种读法：参数互斥，用返回值字段掩盖只会误导模型。
- 网页内容落库做可引用来源：网页会改版、无页码，与"引用必须能回查原文片段"冲突。
- 让摘录模式也命中整页缓存再本地切片：重复实现相关性筛选，质量远低于供应商。
- 缓存 key 不带 user_id：会造成 A 付费、B 白拿额度。

## RATIONALE

工具选择交给 agent，不与 `discover_papers` 绑定；业务服务持有 Key 与缓存，agent 进程不接触秘密。全文进上下文受 `max_chars` 与 offset 约束，翻页不出网。

## OUT OF SCOPE

首次进入引导页、网页作为引用来源、搜索结果落库、in-flight 请求合并、多供应商 adapter、MCP 动态挂载。

## OPEN

供应商可用性只有 Tavily 一家；若大陆网络不可达，替换 `app/web/ports.py` 即可，不改 service 与工具契约。
