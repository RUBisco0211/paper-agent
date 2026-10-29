# 0097 Agent 按页读正文与按块读图

- DATE: 2026-10-29
- TAGS: agent, product, ingest
- STATUS: 当前
- SUPERSEDES: 0042 的 OPEN（片段选择参数、文本预算、Markdown 缺失行为、引用登记关系）；补充 0026 的工具清单

## DECISION

- 新增两个只读工具：`read_paper(paper_id, page)` 读一页解析正文，`read_paper_image(paper_id, block_id)` 读一张图。
- 分页以 MinerU `content_list` 的 `page_idx` 为准，按原文 PDF 页组装 Markdown；不按字符或标题切分整篇 Markdown 冒充页码，单页也不再分批。页码从 1 开始，空白页保留实际页码。
- 单页文本预算 `paper_page_max_chars`（默认 12000 字符，实测本库页面中位数 4211、p95 7316、最大 9145）；超出时按块截断，返回 `truncated`、`partial_block_id`（被截断但部分返回）与 `omitted_block_ids`（完全未返回），不静默丢弃。
- 读页返回可读图片块清单（`block_id`、图注；页码在页面级），正文以 `[图片 | block N | 第P页]` 占位；只有既有图片路径、又在 manifest 中可定位且不超过 `paper_image_max_bytes` 的块才列出，无法读取的块只保留图注。读图一次一张，图片以 base64 `DataBlock` 交给模型，不给对象存储路径。
- 读页内容不登记为引用、不产生 Citation ID；引用只能来自 `search_papers`。系统提示与工具描述都必须写明这一点。
- 系统提示要求先检索后读页；工具描述与系统提示用英文，并明确用用户使用的语言回答。
- 能否附图由当前模型 formatter 的 `supported_input_media_types` 决定；不支持时只返回图注与页码，不落临时文件、不伪造视觉理解。
- 模型目录 `ModelOption` 增加 `supports_vision`，取自 model card 的 `input_types`。

## REJECTED

- 把整篇 Markdown 按字符或标题切分当页码：与原文页码不一致，引用会指错位置。
- 单页再分批或返回续读游标：一页一次已经够用，游标只是多余状态。
- 给模型对象存储路径自行读取：私有存储且需凭据，还会绕过归属校验（0042）。
- 读页内容登记为证据，或允许模型为读页内容自造 Citation ID（0029）。
- 对纯文本模型也返回图片 `DataBlock`：AgentScope 会把 base64 写成临时文件并把路径告诉模型，而本产品没有文件工具（0089）。
- 为读页引入 Redis 缓存：实测 `content_list` 56–187KB、解析不到 1ms、整次读页 6–14ms，瓶颈在存储 GET 而非解析。

## RATIONALE

按页读取让「读第几页」与引用定位共用同一套页码语义；按块读图复用已有的块索引与图片读取路径，不新增解析器。

## OUT OF SCOPE

跨页连续阅读、图表交互、精确区域高亮、图片 OCR、自动通读整篇。

## OPEN

无。
