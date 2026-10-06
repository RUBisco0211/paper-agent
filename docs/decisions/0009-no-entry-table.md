# 0009 不建 Entry 表，会话历史用框架的 messages

- DATE: 2026-10-05
- TAGS: data, agent
- STATUS: 当前
- SUPERSEDES: `docs/overview/minimal-mvp.md` 中「自有 Session + Entry；历史与框架内部 ID 解耦」（该处已同步修改）

## DECISION

不建 `entries` 表。消息与工具结果走 `messages` 表（`(session_id, msg_id)` 复合主键，`payload` JSON，同 key 再写为 replace）。`citation_id` 放 `Msg.metadata`（Msg 的正式 pydantic 字段，不是 payload 里的私有 key）。模型切换只改 `PATCH /sessions/{id}` 的 `chat_model_config` 当前值，不产生历史事件。上下文压缩交给框架的 `ContextConfig`（见 0010）。

## REJECTED

- 自建 `entries` 表做 append-only 时间线：与 `messages` 双写，一致性成本与侵入性都太高。
- 只建极简 `session_events` 记非消息事件：多一张表只换到「时间线显示切换点」这一个收益。
- 把 citation 与模型变化塞进 `payload` 的自定义字段：`payload` 结构归框架所有，它升级改格式就崩。

## RATIONALE

压缩压的是模型看到的输入视图，不是持久化的历史 —— 两者本就不该同表（见 0010）。模型切换的语义天然是「当前值」，与 PATCH 一致；把它历史化只是增加一条没人读的读路径。

## OUT OF SCOPE

会话分支（upsert 语义不支持）、历史编辑、跨会话历史合并。

## OPEN

历史**导出**技术上可行（直接从 `messages` 导出），**未否决，属后置项**——不要当成已否决。其余开放问题：超长会话下 `messages` 表体积与前端首屏加载策略。
