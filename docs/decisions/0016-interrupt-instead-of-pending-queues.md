# 0016 用 interrupt + inbox hint 取代 pending 双队列

- DATE: 2026-10-05
- TAGS: agent
- STATUS: 当前
- SUPERSEDES: `docs/CONTEXT.md` 中 Steering / Follow-up 双 pending 队列的设计（该处已加注）

## DECISION

放弃自建 steering / follow-up 双 pending 队列与 `resume` 端点，改用 `POST /sessions/{id}/interrupt` 与 inbox hint。停止与继续沿用框架的中断语义。

## REJECTED

- 保留自己的 pending 双队列：与它的中断 / 恢复机制并行，两套状态机要互相同步，必然冲突。
- 保留 `POST /v1/sessions/{id}/resume` 处理排队消息：它的恢复语义不同，两套端点会让前端无所适从。

## RATIONALE

中断与 HITL 是框架内建能力，自己维护一套等于重复实现状态机，而且语义更窄。

## OUT OF SCOPE

排队消息的多条管理与编辑、分支式重放。

## OPEN

UI 层是否还需要保留 steering / follow-up 的区分术语（双队列已消失）；interrupt 时被截断的助手消息如何落库与展示。
