# 0054 删除确认弹窗

- DATE: 2026-10-07
- TAGS: frontend, product
- STATUS: 已被 0055 取代
- SUPERSEDES: —

## DECISION

删除定时任务等不可撤销操作沿用项目现有的 `AlertDialog` 确认弹窗。标题点明删除对象，说明写清会一并删除的内容；取消不触发删除，失败留在弹窗内提示。

## REJECTED

- `window.confirm` 浏览器原生确认框：样式与站内弹窗不一致，也无法在弹窗内展示失败原因。

## RATIONALE

项目、会话删除已使用同一组件；定时任务删除保持一致。

## OUT OF SCOPE

其他非删除操作的弹窗布局。

## OPEN

无。
