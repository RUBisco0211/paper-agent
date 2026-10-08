# 0067 会话消息快捷栏

- DATE: 2026-10-08
- TAGS: frontend, chat
- STATUS: 当前
- SUPERSEDES: —

## DECISION

普通会话和定时任务运行会话的消息区左侧显示按消息排列的刻度；当前可见消息的刻度高亮。悬停刻度预览消息文字，点击调用现有 MessageScroller 按消息 ID 滚动。窄屏隐藏快捷栏；消息不足两条时不显示。

## REJECTED

不引入新的滚动库，不复制实现消息滚动状态；不把滚动快捷栏做成另一份会话历史数据。

## RATIONALE

现有 `@shadcn/react/message-scroller` 已提供消息定位与可见消息状态，结合现有 Tooltip 即可完成交互。

## OUT OF SCOPE

持久书签、消息搜索、跨会话导航。

## OPEN

无。
