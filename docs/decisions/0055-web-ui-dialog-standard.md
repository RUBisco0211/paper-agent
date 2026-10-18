# 0055 业务弹窗统一沿用 web_ui

- DATE: 2026-10-07
- TAGS: frontend, product
- STATUS: 当前
- SUPERSEDES: 0054 的弹窗组件选择

## DECISION

所有业务创建、编辑、导入和删除弹窗直接使用 `@/components/ui/Dialog` 的 `Dialog`、`DialogContent`、`DialogHeader`、`DialogFooter`，弹窗内的操作按钮使用 `@/components/ui/Button`。以新建定时任务、对话侧栏删除会话、按 DOI/arXiv 导入的弹窗为视觉锚点：轻遮罩、主题浮层（0080 起采用方角）、右上角关闭按钮、分隔的底部操作区。不可撤销操作在正文说明后果，取消不执行，失败在弹窗内提示。

## REJECTED

- 浏览器原生 `window.confirm`：外观不可控。
- 自有 `@/components/ui/dialog` 或 `@/components/ui/alert-dialog`：遮罩、边框、内边距、按钮和底部区域与 web_ui 不一致；只换成另一套站内组件仍不能统一风格。

## RATIONALE

前端基座是 web_ui（0014、0033）；同类弹窗必须来自同一组件源。

## OUT OF SCOPE

抽屉、菜单、Tooltip 与页面布局。

## OPEN

无。
