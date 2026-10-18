# 0080 SMUI 视觉主题与集中式样式

- DATE: 2026-10-17
- TAGS: frontend
- STATUS: 当前
- SUPERSEDES: 0033 的上游原始视觉约束、0045 的固定配色、0055 的圆角浮层；组件复用与业务交互要求仍有效

## DECISION

采用 [SMUI skill](https://smui.statico.io/skill.md) 的 Nord 深浅配色、JetBrains Mono、方角控件、扩展色板和字号体系，保留 web_ui / Radix 基座、页面布局与业务交互。主题仍跟随系统，由既有 `.dark` 机制驱动，不新增手动切换或 accent picker。

- 唯一运行时主题入口是 `frontend/src/index.css`：`:root` 为 Snow Storm，`.dark` 为 Polar Night；标准 shadcn token 使用完整颜色值，扩展 `--smui-*` 使用裸 HSL，并经 Tailwind 4 映射。
- 全局 CSS 按基础主题、控件、状态、浮层、Tabs、应用布局、输入与工具、动效、引用分组，必要处写中文注释；字体族、字号、字重、圆角、控件密度与交互表面均从这里取值。
- 视觉统一在主题 token、基础组件和共享 variants；业务调用处只编排布局与状态，不追加硬编码颜色、字号、字体、圆角或独立 `dark:` 配色。动态定位和渲染尺寸不属于主题样式。
- 以仓库 `src/globals.css` 为配色基准，不直接采用线上 light/dark 相同的 registry。accent 前景采用 frost-4，状态语义色独立调整明度，确保正文/操作及状态文字在受测背景与 10–20% 叠色表面达到 4.5:1；这不等同于全站 WCAG 认证。
- 字体沿用现有 Fontsource 加载模式，新增本地 JetBrains Mono 字体资源，不依赖 Google Fonts 网络请求；中文使用系统 fallback，正文不套用 11px 标签字号。标签/徽章使用共享大写与字距，卡片使用共享 hover 边框。
- Markdown 的公式样式与 Mermaid 图形配色由共享渲染器集中接入；图中文字、节点与连线引用现有 token，已渲染图随主题变化，不在消息调用点传具体颜色。
- 仅头像、状态点和开关旋钮保留圆形；菜单内边距独立于零圆角，避免点击区域随 radius 归零。
- TextInput 的输入层、测量层、补全层和按钮占位共用几何变量；JS 读取实际 computed 行高，不另存像素副本。既有测试断言随语义变量契约同步，不为旧 class 名保留重复覆盖。
- PDF 原文保持白纸与原始字体；PDF 标注使用独立的白纸配色，聊天引用使用随模式变化的引用 token；坐标和页定位语义不变。

## REJECTED

- 在具体页面或组件调用点堆叠 SMUI 任意值 class、内联主题样式或逐页深浅色分支：视觉来源分散，难维护。
- 覆盖全部 shadcn 组件或搬入 Next.js demo：会丢失现有 API 与聊天能力，并增加无关依赖。
- 全局清除所有元素圆角、把所有白底反色：会破坏头像、状态点及论文原文。

## RATIONALE

Issue #1 的 design 已获用户确认；以既有 token 与基础组件作为集中边界，既统一视觉，也避免重写流式会话与引用功能。验证范围与截图见 [验收记录](../research/smui/smui-theme-validation.md)。

## OUT OF SCOPE

手动主题选择、动态 accent、布局重做、未启用的上游页面、SSE/HITL/引用契约变更、后端功能。

## OPEN

无。
