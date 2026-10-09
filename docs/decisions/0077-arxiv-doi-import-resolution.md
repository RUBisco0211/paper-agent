# 0077 arXiv DOI 导入归一化

- DATE: 2026-10-09
- TAGS: ingest, product
- STATUS: 当前
- SUPERSEDES: —

## DECISION

导入入口将 `10.48550/arXiv.<id>` 及其规范 DOI 链接识别为 arXiv 标识符，按 arXiv ID 查询元数据与 PDF；导入记录使用归一化后的 arXiv 类型和 ID。其他 DOI 继续按 DOI 查询。

## REJECTED

- 所有 DOI 一律交给 Crossref：arXiv DOI 可能没有 Crossref 记录，导致有效论文在元数据阶段失败。
- 在 Crossref 失败后用标题模糊检索代替精确标识符：可能导入错误论文。

## OUT OF SCOPE

自动重试历史失败任务、按标题检索补全文献。

## OPEN

无。
