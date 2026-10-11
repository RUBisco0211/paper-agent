# 0019 摄取：四阶段 + 阶段级重试，能力与状态分离

- DATE: 2026-10-05
- TAGS: ingest, data
- STATUS: 当前
- SUPERSEDES: `docs/archive/prototype.md` §6（已删除）

## DECISION

一次处理 = 一个 Ingestion Job，四个阶段 `metadata / fulltext / chunking / embedding`，每阶段独立记录 `status / attempt / progress / error_code`。Job 状态 `queued / running / succeeded / failed`。重试只重做必要阶段。能力（`has_pdf / has_metadata / has_fulltext / has_keyword_index / has_embedding`）与处理状态分开表达：上游成功、下游失败时已有能力仍然可用。没有 PDF 时不启动正文、分块与向量阶段。

## REJECTED

- 单状态机不分层：无法定位失败位置，重试只能整体重跑。
- 整体重跑：大 PDF 的重解析代价高。
- `cancelled` 态：MVP 不支持解析取消。
- 无限自动重试：鉴权/额度错误必须明确提示而不是重试耗光额度。
- 多解析器自动回退、换 Embedding 模型在线重建：均后置。

## RATIONALE

部分可用是常态（全文好了、向量没好），状态模型必须能表达它，否则界面只能撒谎。

## OUT OF SCOPE

解析取消、多索引版本、用户级重建。

## OPEN

无；worker 启动恢复见 0056。
