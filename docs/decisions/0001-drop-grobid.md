# 0001 去掉 GROBID，元数据走轻量识别 + 在线补全

- DATE: 2026-09-16
- TAGS: ingest
- STATUS: 当前
- SUPERSEDES: `docs/archive/mvp-scope-review.md` 中"以 GROBID 成功/失败作为元数据阶段前提"的旧决定

## DECISION

不部署 GROBID。PDF 元数据用轻量本地提取（前若干页文本与词级布局）得到候选标识符，再走精确在线补全（DOI → Crossref，arXiv ID → arXiv），最后按来源合并字段。识别失败保留占位条目，正文解析继续进行。

## REJECTED

- 保留 GROBID 作为元数据提取主路径：需要额外部署与运维，而本地轻量提取 + 在线补全已能覆盖 born-digital 英文 PDF。
- 用标题/关键词模糊搜索做元数据匹配：标题相近的候选不直接当作同一篇论文，只做候选不落库。
- 让后台补全无条件覆盖已有字段：冲突字段保留来源，用户手动修正优先。

## RATIONALE

元数据成功但全文不可得是正常结果，因此元数据阶段不能成为后续阶段的硬前置。把"已入库"和"元数据完整"分开，能让无 PDF 的条目先存在、后补全文。

## OUT OF SCOPE

多源元数据搜索平台（Semantic Scholar / OpenAlex / PubMed 兜底链）、参考文献解析、自动导入。

## OPEN

本地轻量提取的 Python 库在实施时验证，尚未定稿；补全源目前只有 arXiv 与 Crossref。
