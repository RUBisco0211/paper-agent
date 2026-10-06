# 0020 Chunk 保留页码与版面定位

- DATE: 2026-10-05
- TAGS: ingest, data
- STATUS: 当前
- SUPERSEDES: `docs/archive/prototype.md` §7.2（已删除）

## DECISION

Chunk 必须保留回到原文所需的位置关系：`page_start / page_end`、`block_ids`、`title_path` 与可用坐标。坐标在离线阶段提取，在线引用接口不扫描整份大 JSON。超过 Embedding 模型上限的原子块二次切分并保存子范围，不丢弃也不超限提交。表格保留结构化文本，参考文献单独标型并降低关键词权重。Chunk 可跨页。

## REJECTED

- 只存纯文本不做定位：引用无法回原文。这正是 0006 否决框架 Knowledge Base 的核心理由（它的 chunker 没有页码与版面定位）。
- 在线阶段扫整份 JSON 提取坐标：延迟不可控。
- 丢弃或强行提交超限块：前者丢证据，后者被供应商拒绝。
- 另建独立 layout-index：MVP 不需要（F07 已后置区域高亮）。

## RATIONALE

「点引用能回到原文核对」是这个产品的立身之本，它是数据模型的约束，不是检索的后处理。

## OUT OF SCOPE

区域高亮、坐标换算、章节模糊解析、图表浏览与图表问答。

## OPEN

坐标精度要求；MinerU 版本不兼容时的失败处理（按 0019 记为明确错误，不静默误解析）。
