# 0072 多来源库外文献发现

- DATE: 2026-10-08
- TAGS: agent, retrieval, ingest, frontend
- STATUS: 当前
- SUPERSEDES: 0069 的 OpenAlex 单来源约束；0070 的候选令牌绑定 OpenAlex ID 约束

## DECISION

`discover_papers` 仍是单一只读 Agent 工具。业务服务并发查询 OpenAlex、Semantic Scholar、Crossref；按 DOI 或 arXiv ID 合并候选，不以相同标题单独合并。结果标明命中来源、DOI 与来源明确提供的开放 PDF 地址；PDF 链接供用户查看，不保证下载成功，也不替代入库流程。部分来源失败时保留可用结果并报告失败来源；全部来源失败时报检索服务不可用。候选授权令牌绑定用户、会话、通用来源 URL 与 DOI，沿用用户确认后单次批量入库。

## REJECTED

- 给 Agent 分别开放每个学术来源的工具：跨源去重、错误处理和授权结果会分散到模型行为中。
- 以标题相似度自动合并无共同标识符的候选：不同文献可能同名。
- 把来源提供的 PDF 链接当作已获取全文：链接可能失效或受访问限制。

## RATIONALE

多来源查询缓解单一目录漏检，同时保持现有 Agent 工具和确认入库边界。

## OUT OF SCOPE

领域数据库、复杂加权排序、无 DOI 候选自动入库、PDF 下载来源扩展。

## OPEN

用实际漏检样本评估来源覆盖和排序，再决定领域源及标题匹配策略。
