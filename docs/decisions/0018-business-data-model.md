# 0018 业务数据模型：两层文献结构 + 全局 SHA-256 去重

- DATE: 2026-10-05
- TAGS: data
- STATUS: 当前
- SUPERSEDES: `docs/archive/prototype.md` §4（已删除，业务表部分收在此条）

## DECISION

业务表自建。文献采用两层：`papers` 是全局 PDF 与解析事实（`file_hash` 全局唯一），`user_papers` 是用户可见条目（`UNIQUE(user_id, paper_id)`）。`projects` / `project_papers`（`UNIQUE(project_id, paper_id)`，且 Project 与 User Paper 必须同用户）承载阅读范围。`chunks` 带 `page_start / page_end / block_ids / title_path / search_vector / embedding`。认证三表 `users / auth_sessions / refresh_tokens` 自建。会话与消息归 agentscope（0007 / 0009）。

## REJECTED

- 每个用户一份 paper 副本：同一份 PDF 被重复解析，且无法跨用户复用产物。
- 单表存文献：做不到「全局去重」与「按用户可见性分离」两件事同时成立。
- 用内部 `papers.id` 作对外资源 ID：等于把共享实体身份暴露成越权访问依据。
- 自建 sessions / entries 表：0007 与 0009 已否决。

## RATIONALE

解析成本按文件全局共享，可见性按用户分离 —— 这两件事必须落在两个实体上，任何单表方案都要牺牲其中一个。

## OUT OF SCOPE

字段级迁移策略、多索引版本、软删除、用户级标签与阅读状态（字段归属已定在 User Paper 一侧，但 MVP 不实现）。

## OPEN

表名与字段命名是否沿用；`user_papers` 何时承载阅读状态与标签。
