# 0084 会话公式沿用 Streamdown 数学插件

- DATE: 2026-10-23
- TAGS: frontend
- STATUS: 当前
- SUPERSEDES: —

## DECISION

- 共享 Markdown 渲染器使用 `createMathPlugin({ singleDollarTextMath: true })`，支持 `$...$` 行内公式；块级公式使用 `$$...$$`，起止分隔符各占一行。
- 保留 Streamdown、KaTeX 与现有安全过滤；通过 pnpm override 将间接依赖 `style-to-js` 精确锁定为 `1.1.21`，避免旧版默认导出不兼容导致公式定位样式丢失。
- 自动回归覆盖行内公式、块公式上下标定位及流式矩阵完成后的定位样式；用户已确认实际页面公式渲染测试全部通过。

## REJECTED

- 自写公式解析或排版组件、替换整套 Markdown 渲染器：现有社区插件已提供所需能力。
- 关闭安全过滤或用全局 CSS 补偿错位：不能解决样式转换依赖的导出兼容问题。

## OUT OF SCOPE

新增 LaTeX 分隔符、扩展 KaTeX 环境、改写历史消息或调整 Agent 提示词。
