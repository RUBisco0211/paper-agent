# 0072 多来源库外文献发现与手动检索

- DATE: 2026-10-08（2026-10-09 合并整理）
- TAGS: agent, retrieval, frontend, product
- STATUS: 当前
- SUPERSEDES: 0069、0073

## DECISION

`discover_papers` 是单一只读 Agent 工具；业务服务并发查询 OpenAlex、Semantic Scholar、Crossref，并按精确 DOI 或 arXiv ID 合并候选，不仅凭同标题合并。候选展示来源、书目信息、DOI 与来源明确提供的开放 PDF 链接；该链接不保证可下载，也不等于已有全文。部分来源失败时保留可用结果并报告失败来源，全部失败则报服务不可用。库外候选不进入文献库、不登记 Citation，不能作为 `search_papers` 已解析证据。

全局导航的「在线检索」路由为 `/discover`；用户无需建会话即可通过业务 `/discover-papers` 查询同一聚合来源。手动选中最多 10 篇有 DOI 的候选，在统一弹窗选择全局或项目范围后逐项使用既有 DOI 导入；至少一项受理才打开入库队列。手动检索不使用 Agent 会话绑定的候选令牌。OpenAlex API Key 可选，但匿名请求可能因共享出口额度限流，部署建议配置免费 Key。

## REJECTED

- 为每个来源单独给 Agent 一个工具、让浏览器直连外部学术 API：去重、限流、错误与授权语义会分散。
- 仅凭相同标题合并，或把库外候选/外部摘要分配 Citation：可能误合并，且没有库内原文与页码。
- 为手动检索创建空会话或另一套批量导入模型：已有页面动作与入库任务足够。

## OUT OF SCOPE

通用网页搜索、复杂加权排序、无 DOI 候选自动入库、搜索历史、付费全文。

## OPEN

用实际漏检样本评估来源覆盖和排序，再决定领域源与标题匹配策略。
