# 0030 DOI / arXiv 标识符导入

- DATE: 2026-10-05
- TAGS: product, ingest
- STATUS: 当前
- SUPERSEDES: `docs/overview/minimal-mvp.md` F08（已删除）

## DECISION

输入 DOI、arXiv ID 或对应规范链接；后端规范化后精确查询元数据并尝试下载公开可用的 PDF。元数据查询成功即建条目（0021），再尝试取 PDF；失败保留为「待补全文」，显示原因、原始来源链接、「重新获取 PDF」与「上传 PDF」入口。补传的 PDF 若识别出明确冲突的标识符，提示冲突并保留原数据，不静默覆盖、不自动合并不同文献。人工导入是用户操作，Agent 工具仍只读。

## REJECTED

- 自由标题搜索、任意 URL 爬取、绕过访问限制。
- 把「查无元数据」「无可用 PDF」「来源限流」显示成同一种失败。
- 用 DOI 代替文件身份：同 DOI 的不同 PDF 版本不得混用 Chunk 与页码（0021）。
- 静默覆盖或自动合并冲突文献。
- 因人工导入就顺带给 Agent 开导入权限。

## RATIONALE

导入成功的定义是「元数据入库」，不是「拿到 PDF」——与 0021 是同一条前提。

## OUT OF SCOPE

标题 / 关键词联网搜索（后置）、批量导入、Zotero 同步、Paywall 绕过。

## OPEN

最小来源清单：arXiv 精确查询 + Crossref DOI 起步，其他来源按命中率再加。
