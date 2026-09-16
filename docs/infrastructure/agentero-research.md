# Agentero 的论文工作流与 Agent 工具调研

调研日期：2026-09-16。固定版本：`81ddfe39f59e359cb951c2ebcb6a5bbc25889daf`。对照基线：[Paper Agent MVP 原型](../overview/prototype.md)。本文聚焦论文解析、元数据检索、论文检索，以及面向 Agent 的论文工具；依据官方文档和源码静态阅读，未运行应用或调用付费服务。“借鉴建议”是面向 Paper Agent 的设计判断，尚未变更项目规格。

## 1. 论文解析工作流

### 1.1 从入库到可读正文

Agentero 将本地 PDF、标识符、浏览器 Connector、Zotero 和 CLI 等入口汇入共用的 `paper_commit`：去重、确定目录、初始化论文文件、写入 catalog，再按入口策略下载或解析资源。初始文件与 catalog 登记失败会尝试回滚新目录；后续资源下载、正文解析失败则可保留已入库论文，供再次补齐。命中已有论文时，部分去重分支会修复缺失目录、笔记壳和元数据空字段。[入库实现](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/crates/agentero-core/src/features/paper/import/paper_import/mod.rs)、[导入说明](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/docs/backend/paper-import.md)

正文生成按已有材料选择路径：

```text
论文入库
  ├─ 已有 TeX → 优先使用源文件，不强制生成 PAPER.md
  └─ 已有 PDF、缺少 TeX → 正文解析引擎 → PAPER.md + 派生图片
                                └─ 失败 → 保留 PDF 和论文记录，允许重试
```

解析后记录实际 `body_source` 和 `body_quality`。`PaperCaps` 分别探测 PDF、TeX 和 Markdown 是否可用，用 `needs_paper_md` 等条件决定补处理；“已入库”和“正文可读”是不同状态。[正文流程](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/docs/backend/paper-import.md)、[能力判断](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/crates/agentero-core/src/features/paper/capabilities.rs)

### 1.2 解析引擎与 MinerU

正文引擎采用 `BodyParseEngine` 边界，桌面侧注册 MinerU、Paddle 和 OpenAI 兼容视觉模型等实现；本地引擎使用 liteparse。云端正文适配器复用上传、轮询等基础流程，再转换为 Markdown、图片和来源信息。Agentero 支持云端失败回退本地解析，未注册 backend 也可能回退本地。[引擎注册](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/src-tauri/src/features/paper/analyze/body_engines/mod.rs)、[MinerU 正文适配器](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/src-tauri/src/features/paper/analyze/body_engines/mineru.rs)

MinerU 的具体链路：

```text
申请上传 URL → PUT PDF → 按 batch_id 轮询任务
  → 下载结果 ZIP
  ├─ full.md + images/ → 正文及图片
  └─ content_list.json + middle.json / layout.json → 页面尺寸及版面区域
```

适配器处理结果目录前缀、候选文件名、供应商错误码和轮询期限；限制 ZIP、解压后 JSON、单张图片及图片总量；拒绝不安全图片路径和归一化后的重名图片。源码有格式兼容和路径校验测试。不同调用方共用网络编排函数，不应由此推断正文与版面请求已自动合并为同一次远端任务。[MinerU 实现](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/src-tauri/src/features/paper/analyze/layout/hosted/mineru.rs)

### 1.3 版面产物用于 Agent 阅读与引用

Agentero 把原始版面保存为 `layout.json`，另生成供侧栏、CLI 和 MCP 共用的 `layout-index.json`。索引包含图、表、算法、公式等区域；按区域 ID 可以获取页码、位置和相关信息。Citation resolver 还能把章节、图表、区域或页码链接转换为 PDF 位置，使用 0-based 页索引和 0..1 归一化坐标。[版面索引](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/crates/agentero-core/src/features/pdf/layout_index.rs)、[引用定位](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/src-tauri/src/features/agent/citation.rs)

**对 Paper Agent 的借鉴：**

- 将入库、元数据、正文、分块和索引各自的完成情况分开；重复调用既要去重，也要识别未完成产物。
- 为 MinerU 设置独立适配边界，保留原始结构、Markdown 和图片，增加固定版本样例及产物校验。
- 在解析阶段提取页码、区域与图片关联，使 Agent 后续可以按证据读取正文或图表，不必反复扫描全文。
- 保留 PDF SHA-256 的文件去重；同 DOI 的不同 PDF 版本不能直接共享同一套页码与坐标。
- 当前固定 MinerU 的 MVP 不必同时引入多解析器回退。若未来引入，必须记录实际解析器与质量，不能静默改变引用依据。
- 远端任务 ID 和已验证产物应进入阶段恢复信息，明确重试时继续轮询还是重新提交。Agentero 的 `run_mineru_extract` 中 `batch_id` 是局部变量，这部分恢复设计仍需我们补充。

## 2. 元数据检索工作流

### 2.1 已知 DOI、arXiv ID 或 URL

输入先由 resolver 识别类型并规范化，再构造 Translator 请求；例如 arXiv 输入转换为 `https://arxiv.org/abs/<id>`，避免把 PDF URL 当普通网页解析。Translator 失败时，按标识符走直连补全链路。[标识符 resolver](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/crates/agentero-core/src/features/paper/scholar_api/identifiers/resolver.rs)、[导入说明](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/docs/backend/paper-import.md)

文档列出的主要兜底路径：

| 输入 | 元数据补全路径 |
|---|---|
| arXiv ID | arXiv → Semantic Scholar → alphaXiv |
| DOI | Crossref → Semantic Scholar → OpenAlex |
| PMID | PubMed |

这里的箭头表示来源优先级；部分链路采用错峰并发，并非所有请求都严格串行。元数据解析与 PDF 地址获取分开，查到论文不意味着已获得全文。[标识符查询说明](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/docs/backend/identifier-lookup.md)、[来源接口](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/crates/agentero-core/src/features/paper/scholar_api/traits.rs)

### 2.2 只有本地 PDF

Agentero 先以文件名创建占位论文，后台进行元数据识别：

```text
PDF 前 5 页文本与词级布局
  → Zotero recognizer
  ├─ 识别出 DOI / arXiv → 按标识符查询完整元数据
  ├─ 只有标题和作者 → 使用识别结果
  └─ 未识别 / 服务失败 → 保留占位记录，允许人工补充
```

上传给 recognizer 的是文本布局 JSON；该服务是 Zotero 托管的未公开 API，文档明确定位为尽力而为。识别完成后可规范化论文目录或合并已有条目；若用户已手动编辑元数据，后台结果会放弃覆盖。后续正文与参考文献任务在目录确定后编排。[PDF 元数据识别流程](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/docs/backend/paper-import.md)

### 2.3 对 Paper Agent 的借鉴

值得引入的是“**本地提取候选标识符 → 精确在线补全 → 按来源合并字段**”的工作流，而不是立即替换 GROBID。我们可以让 GROBID 继续负责 PDF 元数据提取，后续在需要时通过 DOI/arXiv 补充缺失字段。

建议把以下规则写进元数据用例：

- 精确标识符查询与标题搜索分开；标题相近的候选不直接当作已确认的同一论文。
- 保存来源及解析版本；联网补全优先填空，对冲突字段保留来源，避免后到结果无条件覆盖。
- 用户修正属于 User Paper 一侧，不应由后台补全改写全局共享事实或其他用户数据。
- 将 metadata 查询、开放 PDF 地址查询、资源下载分开；元数据成功但全文不可得是正常结果。

`AcademicApi`、`PdfUrlSource` 和 `BibliographySource` 分别表达元数据查询、PDF 地址发现和书目导入导出，适合参考这种能力边界。[接口定义](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/crates/agentero-core/src/features/paper/scholar_api/traits.rs)

## 3. 论文检索工作流

### 3.1 联网按标题或关键词发现论文

自由文本进入搜索分支，已识别的标识符进入精确解析分支。搜索返回候选后，再以候选标识符进入入库链路；魔棒查询路径每组默认展示最多 3 个候选，候选含标题、作者、年份、期刊、标识符及来源。[输入路由与候选结构](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/crates/agentero-core/src/features/paper/import/search_router.rs)

```text
标题 / 关键词
  → 根据 SourceScope 选择学术来源
  → 并发请求，各来源独立超时
  → 汇总候选、归并同一论文、合并元数据
  → RRF + 标题匹配 + 来源优先级 + 被引数排序
  → 展示候选 → 选定标识符 → 元数据解析与入库
```

`SourceScope` 支持全部、通用学术、开放获取、预印本、生物医学和自定义来源。实现包含 Semantic Scholar、Crossref、OpenAlex、arXiv、PubMed、alphaXiv；单源搜索预算为 8 秒，S2 match 快路径另有 3 秒预算。排序参数是该版本的实现选择，需要按我们的检索任务重新评测。[搜索聚合](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/crates/agentero-core/src/features/paper/scholar_api/search.rs)

失败处理也属于检索契约：有来源成功时可使用已有结果；全部失败时汇总为限流或网络错误，避免把不可用解释成零命中。**我们的建议**是进一步向调用方提供来源成功/失败状态，标明结果是否降级。[失败汇总](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/crates/agentero-core/src/features/paper/scholar_api/search.rs)

### 3.2 库内查找与正文阅读

Agentero 的论文列表支持查询和标签等过滤；`vault_search` 则遍历 Vault 中的 Markdown，要求所有查询词匹配，返回片段、行号和排序结果。这里核查到的是文件扫描式全文搜索，没有本项目规划的 Chunk 级关键词与向量双通道检索。[论文工具](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/src-tauri/src/integration/mcp/tools.rs)、[全文搜索源码](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/src-tauri/src/features/markdown/search/mod.rs)

其 arXiv 推荐模块使用标题与摘要 embedding，将 RSS 候选与现有论文库比较，并缓存向量；这是论文发现能力，不能作为全文证据检索的等价实现。[推荐模块](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/src-tauri/src/features/paper/discovery/recommend/mod.rs)

**对 Paper Agent 的借鉴：** 清楚区分“搜外部候选论文”“在我的论文库中筛选论文”“在已解析正文中查证据”。外部搜索结果先作为候选，入库并完成解析后才进入正文证据链。当前库内 RAG 继续采用 PostgreSQL FTS + pgvector + RRF；外部论文排序中的被引数权重不直接用于 Chunk 相关性排序。

### 3.3 参考文献作为下一轮发现入口

官方文档描述了先用 Semantic Scholar/Crossref 查询参考文献、再以本地 TeX 的 `.bib`、`.bbl` 或 `thebibliography` 兜底的路径，将结果保存为可重建 sidecar，并支持由参考文献继续导入论文。文档把纯 PDF 文本层参考文献切分列为后置能力。[参考文献解析说明](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/docs/backend/citation-parsing.md)

这可作为后续“读到一篇论文 → 展开参考文献 → 选择相关论文 → 查询并导入”的工作流。这里的书目引用关系与 RAG 回答中的证据 Citation 是两种数据，需分别建模。

## 4. 提供给 Agent 的论文工具

### 4.1 实际 MCP 工具

以下名称来自该版本的 MCP 工具实现，而非为 Paper Agent 拟定的名称。[工具源码](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/src-tauri/src/integration/mcp/tools.rs)、[MCP 工具说明](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/docs/backend/mcp.md)

| 工具 | 功能与关键约束 |
|---|---|
| `paper_list` | 查询和筛选已入库论文；默认仅 `id/path/title`，按 `fields` 或 `full` 展开；默认 50 条、上限 200 |
| `paper_get` | 单篇完整 catalog 元数据，包含摘要 |
| `import_id` | 按 arXiv ID、DOI 或 URL 导入论文，可指定目标父目录 |
| `paper_notes_get` | 读取论文 `NOTES.md`；缺失时返回空字符串 |
| `paper_notes_write` | 替换或追加笔记 |
| `paper_tag_add` / `paper_tag_rm` | 添加或删除标签 |
| `paper_set_read` | 修改已读状态 |
| `layout_list` | 按类型、最低分数列出版面区域，需要已有版面索引 |
| `layout_get` | 按 region ID 获取一个版面区域 |

工具采用结构化输入输出，成功返回 structured content，失败包含稳定 code/message。`paper_list` 的默认轻量返回与 `paper_get` 的详情读取形成渐进取数机制。

**接口边界：** 该 MCP 工具表没有独立的联网标题搜索、正文解析或全文检索工具；不能把后端存在这些能力写成“Agent 已能通过同名 MCP 工具调用”。`paper_notes_get` 读取的是笔记，也不等同于读取论文正文。

### 4.2 CLI 与文件阅读补齐的工作流

本地 Agent 还可以通过 CLI 与 Vault 文件工作。官方 CLI 文档列出 `paper list/get`、`paper download/parse`、`import id`、`layout list/get` 等能力；CLI 的 JSON 列表支持按需字段。其使用指引按任务分流：已有论文路径时直接读文件，探索论文库时才先列论文；未知参数时查询 `describe`。[CLI 说明](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/docs/backend/cli.md)

因此它的 Agent 阅读流程可以概括为：

```text
发现目标论文：列表筛选 / 外部搜索候选
  → 元数据确认：paper_get 或 CLI paper get
  → 准备材料：导入 / 下载 / 解析（按入口与已有能力）
  → 读正文：已有 TeX 或 PAPER.md
  → 看图表：layout_list → layout_get → 对应区域或资产
  → 形成输出：回答 / 写笔记 / 整理标签
```

这是一条跨 MCP、CLI 与文件能力组合的工作流，不是单个 MCP 工具内部完成的操作。版面索引不存在时，布局工具明确返回缺失错误，不会在读取过程中自动完成全部解析。[CLI 布局接口](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/docs/backend/cli.md)、[版面索引读取](https://github.com/poco-ai/Agentero/blob/81ddfe39f59e359cb951c2ebcb6a5bbc25889daf/crates/agentero-core/src/features/pdf/layout_index.rs)

### 4.3 Paper Agent 可以采用的工具划分

下面是设计建议；原型目前只有 `list_papers`、`search_papers`、`get_paper_excerpt` 三个固定只读工具，新增工具仍需后续确定。

| 能力 | 建议契约 | 与现有设计的关系 |
|---|---|---|
| 列举论文 | ID、标题、少量元数据及可用能力，支持分页和总响应预算 | 完善 `list_papers` |
| 查看单篇元数据 | 标题、作者、摘要、标识符、来源 | 可作为详情模式；也可新增 `get_paper` |
| 查找正文证据 | 指定范围检索，返回有限片段、Citation ID、检索状态 | 完善 `search_papers` |
| 展开证据 | 按 Citation/Chunk 返回原文、逐页位置与相关资产 | 完善 `get_paper_excerpt` |
| 阅读图表区域 | 先列区域摘要，再按 ID 获取图注、位置或图片 | 参考 `layout_list/get`，按需要扩展 |
| 外部论文发现 | 返回候选元数据、标识符、来源及部分失败信息，不自动入库 | 后续独立只读工具 |
| 按标识符补全 | 精确解析 DOI/arXiv，返回字段和来源，不隐式下载 | 后续独立用例或工具 |
| 导入、解析、笔记写入 | 明确会改变库状态或触发处理 | 与当前只读工具集分开，后续按产品需求开放 |

核心取舍是让 Agent 按“列表 → 详情 → 证据 → 原文/区域”逐步读取，而不是一次塞入全部论文。用户与项目范围由后端注入；工具共用论文应用层用例，不能因使用 CLI/MCP 风格就绕过 `user_papers` 与项目校验。

检索工具还应区分正常零命中、单通道降级和整体不可用；布局工具区分尚未解析、没有该区域和产物不兼容。所有这些结果都比单纯返回空列表更有助于 Agent 选择下一步。

## 5. 建议优先落地的工作流

1. **上传 PDF → 元数据与正文分别处理 → 产物校验 → 证据可读。** 先补解析能力状态、MinerU 结果契约和定位产物。
2. **列论文 → 看元数据 → 查正文 → 展开引用。** 参考轻量列表与详情分离，完善现有三种只读工具。
3. **标识符 → 多源元数据补全。** 优先使用明确 DOI/arXiv，补全缺失字段并记录来源；标题搜索只产出候选。
4. **标题/关键词 → 多源候选 → 选择 → 入库。** 作为联网论文发现阶段的参考，不与库内证据搜索混为一个接口。
5. **正文 → 图表区域 / 参考文献 → 深入阅读。** 按需求增加布局读取与文献扩展工具，复用已有解析产物。
