# 0074 DOI 导入时查找开放 PDF

- DATE: 2026-10-09
- TAGS: ingest, product
- STATUS: 当前
- SUPERSEDES: 无

## DECISION

DOI 导入先尝试元数据提供的 PDF 链接；缺失或下载失败时，由共用导入服务按精确 DOI 查询 OpenAlex 与 Semantic Scholar 的开放 PDF 地址。逐个下载并经现有 PDF 校验、对象存储和处理流程；首个成功即结束。手动在线检索和 Agent 已确认批量入库共用此流程。全部来源失败时保留已取得的书目信息和 `pdf_unavailable` 状态。检索结果中的 PDF 地址仅供展示，不作为导入请求的可信输入。

## REJECTED

- 在在线检索时下载 PDF：用户可能只浏览候选，下载应在明确入库后执行。
- 由前端或 Agent 传入任意下载 URL：来源和文献身份必须在服务端按 DOI 核对。
- 找不到 PDF 时删除文献条目：元数据条目仍可供用户后续上传全文。

## RATIONALE

Crossref 等元数据源常不返回可下载 PDF，而 DOI 精确匹配的开放来源可补充下载地址。统一放在导入服务，避免手动与 Agent 入库行为分叉。

## OUT OF SCOPE

付费全文、需要登录的来源、没有 DOI 的候选自动入库。

## OPEN

无。
