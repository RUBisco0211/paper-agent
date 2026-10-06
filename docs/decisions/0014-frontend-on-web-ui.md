# 0014 前端基于 web_ui 改造，跟 radix-nova 方言

- DATE: 2026-10-05
- TAGS: frontend
- STATUS: 当前
- SUPERSEDES: 仓库中正在进行的 radix → base 组件迁移

## DECISION

前端以 `examples/web_ui` 为基座改造：React 19 + Vite + Tailwind 4 + shadcn（`radix-nova` 方言）。停掉 base 迁移，避免两套 shadcn 方言合并冲突。0032 的文案规范继续适用（它与组件库无关）；「什么直接沿用、什么自己扩展」的边界见 0033。

## REJECTED

- 保留现有前端只换 API 层：SSE 流、工具调用渲染、中断 UI 都要重新实现一遍，而这些正是重构成本最高的部分。
- 基于 web_ui 但坚持 base 方言：要逐个改它的组件，且每次同步上游都冲突。

## RATIONALE

会话流、HITL、工具渲染是它已经做好的部分，直接继承；产品特有部分（论文库、项目范围、引用卡片）作为自有页面与组件叠加。

## OUT OF SCOPE

它的 i18n（MVP 只留中文）、渠道页面、Skill / MCP 页面、TTS 相关 UI。

## OPEN

现有前端中值得保留的自有组件如何迁进新基座；radix-nova 与现有设计 token 的差异清单。
