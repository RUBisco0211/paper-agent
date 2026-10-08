# 0069 OpenAlex 用于库外文献发现

- DATE: 2026-10-08
- TAGS: agent, retrieval
- STATUS: 当前
- SUPERSEDES: 0041 的三工具白名单、此前暂不做标题/关键词联网搜文献的范围约束

## DECISION

Agent 新增只读 `discover_papers`，经业务服务内部 API 查询 OpenAlex Works；内部 API 先验服务密钥，再按 `session_binding` 验证用户与会话归属。结果仅含候选书目信息和来源链接，不进入用户文献库，不登记 Citation。原三个库内只读工具及范围语义不变。OpenAlex API Key 是可选配置，但匿名请求可能因共享出口额度返回 429；实际部署建议配置免费 Key。

## REJECTED

- 把库外搜索结果当作 `search_papers` 证据或分配 Citation ID：尚无可回查的库内原文与页码。
- 本轮接入普通网页搜索或自动导入：与候选文献发现是不同能力，增加费用和授权范围。

## RATIONALE

库外发现、库内筛选、已解析正文证据各有不同的结果语义。OpenAlex 提供作品搜索，现有内部 API 边界可继续校验调用方和会话归属。

## OUT OF SCOPE

通用网页搜索、自动下载或导入、把外部摘要作为库内引用、跨来源聚合。

## OPEN

无。
