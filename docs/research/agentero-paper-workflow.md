# Agentero 论文工作流与 Agent 工具

- DATE: 2026-09-16（本次改写仅压缩结构，未更新结论）
- STATUS: 当前

固定版本 `81ddfe39`。依据官方文档与源码静态阅读，未运行应用或调用付费服务。

## 结论

可借鉴的是**把入库、元数据、正文、分块、索引各自的完成情况分开**，而不是把它的实现照搬。落到 Paper Agent 的判断：

- 为 MinerU 设独立适配边界，保留原始结构（`content_list.json` / `layout.json`）、Markdown 与图片，加固定版本样例与产物校验；MVP 只固定 MinerU，不引入多解析器回退。
- 元数据走「本地提取候选标识符 → 精确在线补全 → 按来源合并字段」。精确标识符查询与标题搜索分开；标题相近的候选不直接当作同一篇论文；联网补全优先填空，冲突字段保留来源；用户修正属于 User Paper 一侧，后台补全不改写全局共享事实。
- Agent 工具按「列表 → 详情 → 证据 → 原文/区域」渐进读取，不一次塞入全部论文。范围由后端注入，工具共用应用层用例，不能绕过 `user_papers` 与项目校验。
- 保留 PDF SHA-256 文件去重；同 DOI 的不同 PDF 版本不能共享同一套页码与坐标。
- 清晰区分三种检索：**外部候选论文发现 / 库内筛选 / 已解析正文查证据**。库内 RAG 继续用 PostgreSQL FTS + pgvector + RRF；Agentero 外部搜索里的被引数权重不用于 Chunk 相关性排序。

## 依据

- 入库：各入口汇入共用 `paper_commit`（去重 → 目录 → catalog），初始文件与 catalog 失败回滚，后续资源下载/解析失败保留条目供补齐。命中已有论文时部分分支会修复缺失目录与元数据空字段。
- 正文：已有 TeX 优先用源文件；只有 PDF 时走解析引擎，失败保留 PDF 与记录允许重试。解析后记录 `body_source` 与 `body_quality`，「已入库」与「正文可读」是两个状态。
- MinerU 链路：申请上传 URL → PUT PDF → 按 `batch_id` 轮询 → 下载 ZIP（`full.md` + `images/`、`content_list.json` + `middle.json`/`layout.json`）。适配器限制 ZIP、解压后 JSON、单图与图片总量，拒绝不安全图片路径。
- 标识符兜底优先级：arXiv → Semantic Scholar → alphaXiv；DOI → Crossref → Semantic Scholar → OpenAlex；PMID → PubMed。元数据解析与 PDF 地址获取分开，查到论文不代表拿到全文。
- 无标识符时：前 5 页文本与词级布局 → Zotero recognizer（未公开托管 API，尽力而为）→ 识别出 DOI/arXiv 走补全，只有标题作者就用识别结果，失败保留占位。用户已手动编辑时后台结果放弃覆盖。
- MCP 工具（`paper_list` / `paper_get` / `import_id` / `paper_notes_*` / `paper_tag_*` / `paper_set_read` / `layout_list` / `layout_get`）采用结构化输入输出，失败带稳定 code/message。**该工具表没有独立的联网标题搜索、正文解析或全文检索工具。**
- 检索失败属于契约：有来源成功就用已有结果，全部失败汇总成限流或网络错误，不能把不可用解释为「零命中」。

## 备选方案与取舍

| Agentero 能力 | Paper Agent 取舍 |
|---|---|
| 版面索引 + 区域级引用定位 | 后置。MVP 只用已有页码/片段做基础核对，不建独立版面索引、区域高亮或图表交互 |
| 多解析器回退（Paddle / 视觉模型 / liteparse） | 后置。若未来引入，必须记录实际解析器与质量，不能静默改变引用依据 |
| 参考文献解析与续导入 | 后置。书目引用关系与 RAG 证据 Citation 是两种数据，分别建模 |
| 笔记写入 / 标签 / 已读状态等写工具 | 未授权。当前只有三个固定只读工具 |
| `batch_id` 阶段恢复 | Agentero 的 `batch_id` 是局部变量，重试时继续轮询还是重新提交由我们补齐 |

工具契约还应区分：正常零命中 / 单通道降级 / 整体不可用；尚未解析 / 没有该区域 / 产物不兼容。这些比单纯返回空列表更有助于 Agent 选下一步。

## 参考

- [入库实现](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/crates/agentero-core/src/features/paper/import/paper_import/mod.rs)
- [MinerU 正文适配器](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/src-tauri/src/features/paper/analyze/body_engines/mineru.rs) · [Hosted MinerU](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/src-tauri/src/features/paper/analyze/layout/hosted/mineru.rs)
- [标识符 resolver](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/crates/agentero-core/src/features/paper/scholar_api/identifiers/resolver.rs) · [来源接口](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/crates/agentero-core/src/features/paper/scholar_api/traits.rs)
- [MCP 工具](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/src-tauri/src/integration/mcp/tools.rs) · [版面索引](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/crates/agentero-core/src/features/pdf/layout_index.rs)
- [搜索聚合](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/crates/agentero-core/src/features/paper/scholar_api/search.rs) · [CLI 说明](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/docs/backend/cli.md)
