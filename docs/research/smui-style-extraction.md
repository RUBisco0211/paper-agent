# SMUI 样式提取：官方事实与建议

- 访问日期：**2026-10-17**。范围：官方说明、指定源码与本仓库 `frontend/src/upstream` 的定向静态审计；未安装主题或更改前端源码。
- 下文「事实」指已读取的一手来源；「推断」不是 SMUI 官方指令。链接指向访问时的 `main`，不是固定提交快照。

## 1. 结论

**可以提取共性视觉值和重复样式，但“清空所有组件 class、全部迁入全局 CSS”不是所查官方资料展示或要求的做法。** 官方将主题值放到 CSS，Button/Badge 仍用 cva，Card 仍用 Tailwind class；设计指南还直接展示调用处 class 组合。[S1][S2][S3][S4][S5][S6][S7]

## 2. 事实：哪些原本就是全局 tokens

| 类别       | 官方已有内容与位置                                                                                                                                    | 来源         |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| 语义颜色   | `--background/foreground`、`--card` 及前景、popover、primary、secondary、muted、accent、destructive、border、input、ring；`:root` 与 `.dark` 分别赋值 | [S2][S3]     |
| 扩展颜色   | `--smui-frost-1…4`、red/orange/yellow/green/purple、`--smui-surface-0…3`、`--smui-border-hover`；同样有深浅值                                         | [S2][S3]     |
| 图表与侧栏 | `--chart-1…5`、sidebar 背景/前景/primary/accent/border/ring 等；参考 CSS 用 `--sidebar-background`，demo 用 `--sidebar`                               | [S2][S3]     |
| 字体       | 参考 CSS 定义 `--font-sans: 'JetBrains Mono', monospace` 并导入字体；demo 的 `@theme inline` 同时定义 `--font-sans` 和 `--font-mono`                  | [S2][S3]     |
| 字号       | `--text-label: 11px`、`--text-ui: 13px`、`--text-heading: 22px`、`--text-stat: 26px`、`--text-hero: 42px`；demo 用独立非 inline 的 `@theme` 注册      | [S1][S2][S3] |
| 圆角       | `--radius: 0rem`；demo 将 `--radius-sm…4xl` 映射为该变量的偏移或本值，并非每个映射都直接等于零                                                        | [S2][S3]     |

**格式边界：** `src/globals.css` 的语义颜色为裸 HSL 三元组；demo 的语义颜色为完整 `hsl(...)`，通过 `@theme inline` 中 `--color-primary: var(--primary)` 等映射。demo 的扩展 `--smui-*` 颜色仍是裸三元组，映射时包 `hsl(var(...))`。两种格式不能无差别复制。[S2][S3]

## 3. 事实：哪些仍留在组件 Tailwind / cva

| 文件         | 仍由组件负责的样式                                                                                                                                                                               | 来源     |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- |
| Button       | `buttonVariants = cva(...)`：基础排列、gap、`text-ui`、字重、uppercase、tracking、disabled/focus/invalid、SVG；variant 决定颜色与 hover；size 决定 `h-9`、`px-4`、`size-9` 等，仍有 `rounded-md` | [S4]     |
| Badge        | `badgeVariants = cva(...)`：`px-[5px]`、`py-px`、`text-label`、uppercase、tracking、SVG 尺寸、焦点与 invalid；variant 决定底色/文字/边框/hover                                                   | [S6]     |
| Card         | 没有 cva；各子组件在 `cn(...)` 内保留 class。Header 为 `px-3.5 py-2.5` 与下边框，Content 为 `p-3.5`；Title 默认仍是 `leading-none font-semibold`，不是完整的指南标题组合                         | [S5]     |
| 指南调用示例 | CardTitle、Field label、状态 Badge 等重复样式仍以 class 组合展示，含 `tracking-[1.5px]`、`tracking-[2px]`、5px 状态点、颜色透明度等                                                              | [S1][S7] |

`bg-primary`、`text-muted-foreground`、`text-ui` 等虽然写在组件里，消费的已经是全局主题值；**不能把“组件中有 class”直接等同于“视觉值写死”**。另一方面，间距、字重、字距、尺寸和部分透明度仍在组件或示例中指定；所查文件没有为每个值建立 SMUI 专用 token。[S3][S4][S5][S6][S7]

## 4. 事实：官方确实抽到了全局 CSS 的规则

- demo 全局 CSS 包含 base 层默认边框/outline、body 背景与文字色，以及 `.card-glow` 的 hover 边框过渡。[S3]
- `.skeleton` + `shimmer`、`.cursor-blink` + `blink`、`::selection` 和 Shiki 深浅代码色规则也在 demo 全局 CSS；动画时长等仍直接写在规则中，并非全部参数化。[S3]
- skill 明确给出全局字号注册、扩展颜色映射、`.card-glow` 与 selection 样式，并要求扩展 `tailwind-merge` 的 font-size 分组，避免自定义 `text-*` 字号与颜色合并冲突。[S1]
- README 支持直接复制 CSS 变量作为安装方式；本次只阅读，没有执行安装命令。[S8]

## 5. 推断：可提取边界（不是官方要求）

| 建议                                                                                 | 依据与限制                                                                                                                     |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| 优先集中颜色、字体、字号、圆角与语义状态色                                           | 这些已有官方 token；应先复用而非新增第二套值。具体本仓库是否已接入，留给主代理核对。[S2][S3]                                   |
| 重复的标题/标签/状态组合可收敛为共享 variants、基础组件或显式语义 CSS class          | 指南承认这些重复模式，但本身仍以 class 组合呈现；“把它们继续抽取”是项目维护策略，不是官方强制方案。[S1][S7]                    |
| 反复出现、需要整体调节的字距/控件高度/内边距，可考虑新增项目 token                   | 官方组件仍保留这些数值；是否值得参数化应以本仓库重复程度与统一调整需求为依据，不给每个 Tailwind 数值机械新增变量。[S4][S5][S6] |
| 保留组件的布局、状态、尺寸和 variant 归属，不为减少 class 数量而全部迁移到全局选择器 | 与官方 cva/组件示例一致；若全迁 CSS，需要自行维护 variant、状态、覆盖顺序和隔离边界，不能宣称这是官方迁移要求。[S4][S5][S6]    |
| 共享规则优先显式挂载，避免宽泛覆盖 `button`、`span` 等标签                           | 官方用 `.card-glow` 显式启用该效果；“避免宽泛覆盖”是由此提出的维护建议，而非原文禁令。[S1][S3]                                 |

### 文档与实现差异，不能忽略

- 色值以具体版本源码为准：例如指南的浅色 `--card` 为 `218 27% 92%`，所读两个 CSS 文件均为 `218 27% 89%`；skill 的十六进制表也不宜视为与源码逐项完全同步的精确值。[S1][S2][S3][S7]
- 文档强调零圆角，但 Button 仍写 `rounded-md`，demo 仍保留圆角派生公式；仅看到 `--radius: 0rem` 不能据此断言所有 class 的最终计算圆角为零，需要实际编译/浏览器核验。[S1][S3][S4]
- “不主张抽空所有 class”的准确含义是：**所查来源没有这项要求，且实际源码保留大量组件 class**；不是声称官方明确禁止 CSS 提取。[S1][S4][S5][S6][S7]

## 6. 本项目具体建议

审计基准：`feature/smui-theme` / `679978f`。以下路径相对 `frontend/src/upstream/`；名称是候选设计，不是已实现的变量，也不是 SMUI 官方 token。现有主题与约束见 `index.css` 和决策 0080。

### 已集中，无需另建一套

`index.css` 已有语义颜色、扩展 SMUI 色板、字体与字号、tracking-label、radius 派生值、状态文字色、引用色、panel/tab 阴影；优先复用。`text-ui`、`bg-primary`、`rounded-lg` 都已消费全局值，不因出现在 TSX 中就需要搬走。

### 第一批：共性视觉 token 与共享规则（推荐）

| 可集中内容     | 候选 token / 维护位置                                                                | 当前证据与注意点                                                                                                                                                                                 |
| -------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 浮层遮罩       | `--overlay-backdrop`、`--overlay-blur`                                               | `components/ui/dialog.tsx:32`、`sheet.tsx:32` 都写 `bg-black/10` 与 blur；颜色与模糊可全局，开闭方向与 Portal 仍归组件                                                                           |
| 浮层边界与阴影 | `--floating-border`、`--shadow-floating`                                             | `dialog.tsx:54`、`dropdown-menu.tsx:36`、`popover.tsx:27`、`chat/QuoteBadge.tsx:44`、`chat/ASMessageBubble.tsx:565` 反复出现 ring-foreground/10、shadow-md/lg；shadow-panel/tab 已有，勿重复定义 |
| 控件状态表面   | `--control-hover-bg`、`--control-active-bg`、`--control-disabled-bg`                 | `components/ui/button.tsx:13–20`、`input.tsx`、`select.tsx` 有 opacity 与 dark 分支；应按语义收敛，outline/ghost/destructive 不必强行共用同一个 hover                                            |
| 焦点与禁用反馈 | `--focus-ring-width`、`--focus-ring-color`、`--disabled-opacity`                     | Button/Input/Select 的 ring-3、ring-ring/50、opacity-50 是共性视觉，可由主题值驱动，focus/disabled 选择器仍在基础组件                                                                            |
| 状态徽章表面   | `--success-subtle`、`--success-border`，warning/destructive 同理；现有状态文字色复用 | `components/badge/StatusBadge.tsx`、`pages/imports/ImportQueuePanel.tsx`、项目的 PaperStatusBadge 还各自组合状态样式；优先用基础 Badge/shared variants 归拢，再统一表面值；保留叠色对比度测试    |
| 动效节奏       | `--motion-duration-fast`、`--motion-duration-normal`、`--motion-ease-standard`       | `components/ui/dialog.tsx` 的 100ms、`sheet.tsx` / `sidebar.tsx` / `pages/chat/ChatPage.tsx` 的 200ms、CSS 中 150/180/200ms；不是所有动画都应同速，继续支持 reduced-motion                       |

### 第二批：统一密度与应用几何（有整体调节需求再做）

| 可集中内容                     | 候选 token / 维护位置                                                           | 当前证据与注意点                                                                                                                                                                      |
| ------------------------------ | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 控件高度、横向内边距、图标尺度 | `--control-height-xs/sm/md/lg`、`--control-padding-inline`、`--icon-size-sm/md` | `components/ui/button.tsx:24–34` 的 h-6/7/8/9、size-6/7/8/9，与 Input/Select 的尺寸；size variants 继续属于基础组件，不把每个 px/gap 都单独变成全局变量                               |
| 共享文字角色                   | 复用 `--text-label/ui/heading`，按需求增加 `--text-body`、`--leading-body`      | 相同 text-sm 有不同角色，不能全量替换；标题/说明/元数据应通过已有组件或共享 variants 指定角色                                                                                         |
| 工具栏与导航宽度               | `--app-toolbar-height`、`--app-nav-rail-width`                                  | `pages/chat/ChatPage.tsx:119` 的 h-12；`components/layout/AppSidebar.tsx:29` 的 w-16 多处覆盖；其他业务页面也有统一 48px 顶栏                                                         |
| 会话内容最大宽度               | `--chat-content-max-width`                                                      | `pages/chat/NewChatPage.tsx`、`PaperChatPage.tsx` 的 max-w-3xl；属于产品统一阅读宽度，可集中，不把所有弹窗 max-width 合并                                                             |
| 侧栏默认宽度                   | 优先复用已有 `--sidebar-width`、`--sidebar-width-icon`；必要时按应用角色映射    | `components/ui/sidebar.tsx:25–27` 有 16/18/3rem 默认值；Provider 内联赋值、AppLayout 覆盖与具体 w-64 必须一起核对，否则加 root token 仍会被局部覆盖。拖拽后的运行时宽度不转为静态 CSS |

### 组件局部 CSS 变量，避免污染 root

- Dialog 的 `--dialog-padding` 应同时驱动 content 的 padding 与 footer 的负 margin（`components/ui/dialog.tsx:54,95`），否则改一处会错位；它适合默认值在共享 Dialog 的 slot 中定义，不一定全局发布。
- `--composer-min-height`、`--composer-line-height`、`--composer-padding-inline/block`、最大行数适合绑定共享 TextInput。当前 21px 行高、52px 收起高度、六行上限和 12px 横向留白写在 `components/chat/TextInput.tsx:102–114`，并被 textarea、补全 overlay、测量 ghost、按钮行共同使用（402–483 行）。必须让测量算法读到同一份计算值，不能仅搬显示样式。
- `--tool-preview-max-height` 可承接 `components/chat/ConfirmCard.tsx:82` 的 200px 预览上限；只在该类工具预览间共享，不给所有滚动区套同一高度。

### 抽重复组合，而不只是抽变量

建议将浮层 chrome、工具确认面板、输入框壳、页面工具栏的重复组合收敛为基础组件/shared variants，必要时使用显式语义 class 或 data-slot 的 `@layer components`。CSS 变量回答“取什么值”，共享样式回答“哪些规则一起使用”；只增加变量但保留调用处几十个组合，维护问题不会消失。

不能仅在全局添加一个低层级选择器然后保留原来的 utility 覆盖。Tailwind utilities 会覆盖 components 层；内联 style 又可能覆盖普通规则。迁移时应删除被取代的旧覆盖，不用全局 `!important` 压制，并保持 variant/size interface 不变。

### 不建议提到全局

flex/grid 结构、truncate、overflow、sr-only、响应式显示规则、aria/data 状态条件、Radix transform-origin/available-height 变量、滚动定位、canvas/PDF 坐标、JS 测量的最终高度与拖拽尺寸。`FlipCard.tsx:15–30` 的透视/transform 属性可放组件局部 CSS，但 Framer Motion 的旋转与退出状态仍由动画逻辑管理。

优先级建议：先做第一批且默认外观不变；再按确切的密度/几何调整需求做第二批；TextInput 测量耦合单独验证。不要扩大到尚未启用的 Skill/MCP/channel 等上游残留页面。

## 7. 一手来源

以下均于 **2026-10-17** 访问；S1–S8 正文均已读取。

- [S1] 官方 agent skill：<https://smui.statico.io/skill.md>
- [S2] 官方参考变量 CSS：<https://github.com/statico/smui/blob/main/src/globals.css>
- [S3] 官方 demo 全局 CSS：<https://github.com/statico/smui/blob/main/demo/src/app/globals.css>
- [S4] 官方 demo Button：<https://github.com/statico/smui/blob/main/demo/src/components/ui/button.tsx>
- [S5] 官方 demo Card：<https://github.com/statico/smui/blob/main/demo/src/components/ui/card.tsx>
- [S6] 官方 demo Badge：<https://github.com/statico/smui/blob/main/demo/src/components/ui/badge.tsx>
- [S7] 官方设计指南：<https://github.com/statico/smui/blob/main/AESTHETIC.md>
- [S8] 官方 README：<https://github.com/statico/smui/blob/main/README.md>

验证范围：一手文档与源码交叉核对、宿主入口和代表组件静态检查；仅新增本报告，不运行应用测试或视觉验证。

## 实施状态补充

用户已确认在 PR #2 落实两批抽取；全局变量按模块集中维护，运行时几何保留在组件。结果和边界见 [验收记录](smui-theme-validation.md)；上文针对 679978f 的源码位置是抽取前审计快照。
