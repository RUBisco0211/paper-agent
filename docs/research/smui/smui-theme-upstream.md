# SMUI 官方主题调研

- 访问日期：**2026-10-17**。
- 范围：仅 statico/smui 官方 GitHub 仓库（含其 raw 文件、提交与 releases 页面）及 https://smui.statico.io；未引用第三方介绍、未访问第三方依赖文档。
- 方法：fetch 阅读文档与源码；terminal 用 Python 标准库获取原始 HTTP 响应、解析 JSON、比较副本并计算 SHA-256。未执行安装、构建或浏览器视觉测试；不声称已验证 shadcn CLI 的实际落盘行为。
- 标记：**事实**为已读取来源或直接比较结果；**推断/建议**为基于这些事实的迁移判断；**未验证**为本次来源或操作不足以确定的事项。

## 1. 主要结论

| 类型 | 结论 | 来源 |
|---|---|---|
| 事实 | SMUI 是 shadcn/ui 的主题与视觉规范，不是必须接入的独立 React 组件运行时；README 同时提供 registry 安装与手工复制 CSS 两种路径。 | [README][S1]、[registry][S4] |
| 事实 | **推荐安装 URL 当前不是双配色主题**：线上 JSON 的 `cssVars.light == cssVars.dark`，两者都是深色值；仓库顶层 registry 的两者则不同。 | [线上 registry][S5]、[仓库 registry][S4] |
| 事实 | 线上 JSON 与仓库 `demo/public/r/spacemolt-theme.json` 语义一致，字节 SHA-256 也相同；问题并非只在网页文字展示。 | [线上 registry][S5]、[demo 静态副本][S6] |
| 推断/建议 | 可以借用配色，但不宜直接把官网安装命令当作完整迁移方案；应选择经审核的源码快照、统一 token 格式并保留宿主组件行为。 | 依据：[S1][S4][S5][S9][S14][S15] |

## 2. 主题安装产物与不包含的内容

| 类型 | 核实结果 | 来源 |
|---|---|---|
| 事实 | 官方命令为 `npx shadcn add https://smui.statico.io/r/spacemolt-theme.json`；README 允许直接复制 CSS variables。这里只记录命令，未执行。 | [S1] |
| 事实 | 顶层 registry 与线上 registry 的顶级字段均为 `$schema`、`name`、`type`、`cssVars`；`name` 为 `spacemolt`，`type` 为 `registry:theme`。 | [S4][S5] |
| 事实 | 两份 registry 均无 `files`、`dependencies`、`devDependencies`、`registryDependencies`、`css` 字段；声明的是主题变量，不包含 TSX 组件、Provider 或交互逻辑。 | [S4][S5] |
| 事实 | `cssVars.theme` 仅提供 `font-sans: 'JetBrains Mono', monospace`；light/dark 提供基础语义色、5 个 chart 色、sidebar 色与 `radius: 0rem`。 | [S4][S5] |
| 事实 | registry 不含 `--smui-*` 扩展色、四级 surface、`--text-*` 字号、字体文件或加载代码，也不含 `card-glow`、shimmer、selection 样式。官网将扩展 palette 与 utility CSS 作为额外手动步骤。 | [S4][S5][S7] |
| 推断 | “一条命令让整个界面变成展示站”只能对已消费相应 tokens 的样式成立；标签大写、间距、组件 variants、阴影与硬编码圆角不会因为 JSON 声明而自动全部改变。 | 依据：[S2][S4][S14][S15][S16] |
| 未验证 | 不确定任意 shadcn CLI 版本对任意宿主 CSS 的具体合并、覆盖与落盘结果；本次没有运行 CLI，不把 registry 内容等同于已发生的文件改动。 | 核验边界；输入来源：[S4][S5] |

## 3. CSS tokens 与官方来源间漂移

| 类型 | 核实结果 | 来源 |
|---|---|---|
| 事实 | `src/globals.css` 的基础色、chart、sidebar、扩展色均用裸 HSL 三元组，例如 `--background: 218 27% 94%`，消费颜色时需要 `hsl(var(...))`；还声明 `--radius: 0rem`、`--font-sans` 与字号变量。 | [参考 CSS][S3] |
| 事实 | 扩展色包括 `--smui-frost-1..4`、red/orange/yellow/green/purple、`--smui-surface-0..3`、`--smui-border-hover`；参考 CSS 为浅色扩展色提供较暗值，深色提供另一组值。 | [S3] |
| 事实 | demo 的基础语义色、chart 与 sidebar 则保存完整颜色值，如 `--background: hsl(218 27% 94%)`，其 Tailwind 映射为 `--color-background: var(--background)`；仅 `--smui-*` 继续使用裸 HSL 并在映射中包 `hsl()`。 | [demo CSS][S9] |
| 事实 | registry/参考 CSS 使用 `sidebar-background`，demo 使用 `--sidebar` 并映射到 `--color-sidebar`；这不是同一个变量名。 | [S3][S4][S9] |
| 事实 | 设计文档的“全局零圆角”不是所有 demo 半径的实际数值保证：demo 的 `--radius-xl` 为 `calc(var(--radius) + 4px)`，更大的等级继续增加；源码也保留部分 shadow 类。 | [S2][S9][S14][S16] |
| 推断/建议 | 不要直接混贴三类产物。裸 HSL 被完整颜色消费者读取，或完整颜色被再次包入 `hsl()`，会造成无效颜色；sidebar 命名也需映射。零圆角需检查使用的半径等级和固定类，而不只改 `--radius`。 | 依据：[S3][S4][S9][S14][S16] |

### 可复核的数值差异

下表是实际来源值，不用文档中的 hex 近似替代 CSS 值。

| token / 情况 | 仓库 registry / 参考 CSS | 其他官方来源 | 类型与来源 |
|---|---|---|---|
| 浅色 `background` | `218 27% 94%` | 线上 registry 的 light 为 `213 16% 12%` | 事实：[S3][S4][S5] |
| 浅色 `primary` | `213 32% 40%` | AESTHETIC 为 `213 32% 44%`；线上 registry 的 light 为 `193 44% 67%` | 事实：[S2][S3][S4][S5] |
| 浅色 `card` | `218 27% 89%` | AESTHETIC 为 `218 27% 92%` | 事实：[S2][S3][S4] |
| 浅色 `--smui-green` | 参考 CSS 为 `92 35% 34%` | AESTHETIC 为 `92 35% 38%`；官网手动扩展片段在 `:root` 使用 `92 28% 65%`，未另给浅色 aurora 覆盖 | 事实：[S2][S3][S7] |
| 深色 `chart-2` | registry 为 `213 32% 44%`；参考 CSS 为 `213 32% 52%` | 线上 registry 与 demo CSS 均为 `213 32% 52%`（demo 外包 `hsl()`） | 事实：[S3][S4][S5][S9] |

**推断/建议：**README、skill 与设计指南对“双模式、对比度调整”的表述不能代替产物核验；应明确选定哪个文件为数值基准，不能把这些官方来源视为完全同步。未做 WCAG 比值、键盘可访问性或浏览器实测，不将“官方声称 contrast-adjusted”写成已认证可访问性。[S1][S2][S3][S4][S5][S7][S8]

## 4. 深浅模式与运行时 accent

| 类型 | 核实结果 | 来源 |
|---|---|---|
| 事实 | 参考 CSS 通过 `:root` 定义 Snow Storm 浅色，通过 `.dark` 覆盖 Polar Night 深色；该文件本身没有自动监听系统偏好的 `prefers-color-scheme` 规则。 | [S3] |
| 事实 | 官方指南与 skill 推荐 `ThemeProvider attribute="class" defaultTheme="dark"`；demo 进一步明确 `enableSystem={false}`。 | [S2][S8][S10] |
| 事实 | demo 的 ThemeSwitcher 用 `useTheme()` / `setTheme()` 切换 light/dark，挂载前先返回占位按钮；layout 使用 `suppressHydrationWarning`。 | [S11][S12] |
| 事实 | runtime accent 是单独的 React 组件：它读取 `resolvedTheme`，在 `document.documentElement.style` 修改 primary、ring、sidebar、chart 等变量；浅色模式约束 accent 的饱和度与亮度，切换模式时重新应用。registry 不包含它。 | [accent picker][S13]、[S4][S5] |
| 事实 | AccentPicker 给基础变量写完整 `hsl(...)`，给 `--smui-frost-2` 写裸 HSL；这与 demo 的混合格式对应，而非参考 CSS 的全裸 HSL 格式。 | [S3][S9][S13] |
| 推断 | 对当前线上 registry，即使正确切换 `.dark`，仅靠该 JSON 也无法产生两套不同基础配色；对原始参考 CSS，则不必使用 next-themes，只要宿主正确管理 `.dark` 类即可切换。 | 依据：[S3][S5][S10] |
| 推断/建议 | 若移植 accent picker，必须同时适配变量格式、模式变化与对比度；CSS 自身不会提供颜色选择器或偏好持久化逻辑。 | 依据：[S3][S4][S13] |

## 5. Tailwind / React / Next.js / next-themes 耦合与依赖

| 层级 | 已验证事实 | 迁移判断（推断） | 来源 |
|---|---|---|---|
| 原始主题变量 | 参考 CSS 是 CSS custom properties、选择器与字体 `@import`，无 React/Next.js 导入；registry 未声明 npm 依赖。 | 只采用 tokens 不要求安装 React、Next.js、next-themes 或 Radix。 | [S3][S4][S5] |
| Tailwind 工具类 | 指南使用 Tailwind v4 的 `@theme inline` 映射颜色，独立非 inline `@theme` 注册 11/13/22/26/42px 的字号。demo 使用 Tailwind `^4`。 | 全套示例依赖相应 Tailwind 配置；其他工具链可借用 CSS 值，但示例工具类不是即贴即用。 | [S2][S8][S9][S17] |
| class 合并 | skill 要求为自定义 `text-label/text-ui/text-heading/text-stat/text-hero` 扩展 tailwind-merge 的 font-size class group；demo `cn()` 已实现。 | 若复用自定义字号与 `cn()`，需同步合并配置；仅复制 colors 不需要该额外动作。 | [S8][S18] |
| React 交互 | AccentPicker、ThemeSwitcher 与 ThemeProvider 是 React 客户端组件，后两者及 picker 使用 next-themes。 | 复制这些实现才引入其 React/next-themes 耦合；不能反推主题 CSS 有同样硬依赖。 | [S10][S11][S13] |
| Next.js | demo 为 Next `16.1.6`、React/React DOM `19.2.3`；字体示例和实际 layout 使用 `next/font/google`。 | 这是示例应用技术栈，不是主题必须迁移到 Next.js 的证据；非 Next 宿主应替换字体加载方式。 | [S12][S17] |
| demo 组件与工具 | demo 依赖还有 `class-variance-authority`、`clsx`、`cmdk`、`lucide-react`、`radix-ui`、`shiki`、`tailwind-merge`；devDependencies 含 `@tailwindcss/postcss`、`tw-animate-css`、`shadcn` 等。根 package.json 无 dependencies/devDependencies。 | 不应整份拷贝 demo 的依赖清单；语法高亮、命令面板和图标依赖不等于配色依赖。 | [S17][S19] |
| 动画与工具 | demo CSS 导入 `tailwindcss`、`tw-animate-css`、`shadcn/tailwind.css`；README 的 Playwright、ffmpeg 用于生成截图 GIF。 | 这些不是仅采用 CSS tokens 必须携带的运行时依赖。 | [S1][S9] |

## 6. 字体与中文

| 类型 | 核实结果 | 来源 |
|---|---|---|
| 事实 | 视觉规范要求 JetBrains Mono、等宽文本、大写英文标签与宽字距；常用正文 `text-sm`，标签 `11px`，界面文字 `13px`。 | [S2][S8] |
| 事实 | registry 只设置 `font-sans`，不下载字体；参考 CSS 通过 Google Fonts `@import` 加载 JetBrains Mono（300–700 常规及 400 斜体，`display=swap`），fallback 为通用 `monospace`。 | [S3][S4][S5] |
| 事实 | demo layout / 官方示例使用 `next/font/google`，指定 `subsets: ["latin"]`、300–700 字重；demo CSS 同时设置 `font-sans` 与 `font-mono`，layout 的语言为 `en`。 | [S7][S9][S12] |
| 未验证 | 已查官方材料未提供中文专用 font stack、CJK 字体产物、字形覆盖清单或中文排版验收。本次没有检查字体二进制，不能仅凭 `latin` 配置断言字体文件绝对不含任何汉字，也不能声称已保证中文覆盖。 | 核验依据与范围：[S2][S3][S7][S8][S12] |
| 推断/建议 | 中文不能直接承诺“JetBrains Mono everywhere”：应显式设计中文 fallback，并检查中英混排的字宽、行高、换行、小字号可读性与字距；大写规则对汉字没有对应的大小写转换效果。 | 依据：[S2][S3][S8][S12] |
| 推断/建议 | 直接复制参考 CSS 会引入外部 Google Fonts 请求，应考虑部署网络、隐私与离线可用性；采用本地字体资源或另一加载方式需要单独落实。字体与第三方包的许可不能从 SMUI 的 Unlicense 一并推定，本次未越出指定来源核实。 | 依据：[S3][S12][S20] |

## 7. 组件是否重写

| 类型 | 核实结果 | 来源 |
|---|---|---|
| 事实 | registry 没有组件文件，主题安装不声明替换组件。官网称展示为“Standard shadcn/ui components styled with the smui theme”。 | [S4][S5][S7] |
| 事实 | demo 中保留 shadcn 风格的本地 React 包装组件：Button 使用 CVA 与 Radix Slot，Tabs 和 Dialog 包装 `radix-ui` 的 primitive，而非 SMUI 自写一套底层交互。 | [S14][S15][S16] |
| 事实 | demo Button 的基础 class 已包含 `text-ui uppercase tracking-wider`；Tabs 提供 `line` variant 与大写/字距样式。指南也要求额外组件布局、卡片 header 间距及状态 badge 类。 | [S2][S14][S15] |
| 事实 | 指南还给出手写 div 的 toggle 与 dialog 外观片段；这些是设计示例，并非 registry 提供的可访问性交互实现。demo 实际 Dialog 仍使用 Radix primitive。 | [S2][S4][S16] |
| 未验证 | 未对比任一指定版本的原始 shadcn 源码，因此不能精确量化哪些 class 是 SMUI 改写、哪些来自对应生成版本；“组件全部没改”与“全部重写”均无依据。 | 比较边界；已读取实现：[S14][S15][S16] |
| 推断/建议 | 采用主题无需重写业务组件；若追求展示站一致的密度和排版，则需有选择地调整样式，而不是覆盖宿主已有组件、primitive、Dialog、Button 或无障碍行为。迁移到不同组件库时尤其不能机械复制 Radix 包装层。 | 依据：[S2][S4][S14][S15][S16] |

## 8. License、维护与交付风险

| 类型 | 核实结果 | 来源 |
|---|---|---|
| 事实 | README、根 package.json 与 LICENSE 声明 Unlicense；许可证允许复制、修改、发布、使用、编译、销售、分发，并包含 AS IS、无担保及责任限制。 | [S1][S19][S20] |
| 事实 | 根 package.json 版本为 `1.0.0`；安装 JSON 本身无版本字段；GitHub releases 页面显示没有 release。package 版本不能当成网站产物的发布版本。 | [S4][S5][S19][S21] |
| 事实 | 访问时 GitHub 页面显示 35 commits；main 最新可见提交为 2026-08-12 的 `b917de0`（更新 SpaceMolt 链接），之前 2026-02-19 有 light mode contrast / accent 修复，2 月 18 日有添加 light mode 的提交。 | [仓库][S22]、[提交历史][S23] |
| 事实 | 已有可直接复核的同步问题：仓库 registry 与网站静态副本分叉、指南与参考 CSS 数值不一致、demo 和参考 CSS 的基础 token 格式不同。 | [S2][S3][S4][S5][S6][S9] |
| 推断 | 维护风险主要是多份手工产物漂移与缺少可辨识 release 的交付边界，不是已证实的依赖安全漏洞；也不能据提交间隔就断言项目已弃用。 | 依据：[S4][S5][S6][S19][S21][S23] |
| 推断/建议 | 适合把审核后的配色/设计规范作为可控快照引入；不宜不加检查地自动跟随 main 或线上 URL。字体和依赖另做许可清点；保留采用文件、commit 与差异记录，避免以后无法复现。 | 依据：[S3][S4][S5][S17][S20][S21][S23] |

## 9. 原始响应核验记录与未做事项

**事实：**terminal 对线上安装 URL 得到 HTTP 200、`Content-Type: application/json; charset=utf-8`；直接 `json.loads()` 后比较 `cssVars.light` 与 `cssVars.dark` 为 `True`。同样比较顶层仓库 registry 为 `False`，demo 静态副本为 `True`。[S4][S5][S6]

| 响应 | SHA-256（访问时字节） | 来源 |
|---|---|---|
| 仓库顶层 registry | `6942de39a3460ef63183b08449846a7dfb14a924ec4b60d5d87747e0f403ea2a` | [S4] |
| 线上 registry / demo 静态 registry（相同） | `2687e3a4a027cf029ce0a2ecfadd1d86b31b3bbc39c982298dc795fc55fc629c` | [S5][S6] |
| 仓库 skill（与线上逐字节相同） | `61a2053cade89fee9feace285d77b7454052ed57398d9d20dec9e3209f36e1ad` | [S8][S24] |

- 未执行安装，因此未验证 CLI 兼容矩阵、实际 CSS 合并与版本相关行为；未运行浏览器、WCAG/中文字体测试、供应链安全扫描或项目迁移。
- GitHub REST API 的仓库信息请求返回 HTTP 403 rate limit exceeded；维护信息改用官方 GitHub HTML 页面核实，不据此虚构 API 数据。
- `main` 与网站均为可变来源，上述结论是访问日快照；哈希用于核对读取内容，不代表网站承诺版本固定。
- 本报告不读取或评估 Paper Agent 前端实现，因此不把任何宿主框架、token 格式或具体迁移改动当作已核实事实。

## 来源索引（均为官方一手来源，访问日期 2026-10-17）

[S1]: https://raw.githubusercontent.com/statico/smui/main/README.md
[S2]: https://raw.githubusercontent.com/statico/smui/main/AESTHETIC.md
[S3]: https://raw.githubusercontent.com/statico/smui/main/src/globals.css
[S4]: https://raw.githubusercontent.com/statico/smui/main/registry/spacemolt-theme.json
[S5]: https://smui.statico.io/r/spacemolt-theme.json
[S6]: https://raw.githubusercontent.com/statico/smui/main/demo/public/r/spacemolt-theme.json
[S7]: https://smui.statico.io
[S8]: https://smui.statico.io/skill.md
[S9]: https://raw.githubusercontent.com/statico/smui/main/demo/src/app/globals.css
[S10]: https://raw.githubusercontent.com/statico/smui/main/demo/src/components/theme-provider.tsx
[S11]: https://raw.githubusercontent.com/statico/smui/main/demo/src/components/theme-switcher.tsx
[S12]: https://raw.githubusercontent.com/statico/smui/main/demo/src/app/layout.tsx
[S13]: https://raw.githubusercontent.com/statico/smui/main/demo/src/components/accent-picker.tsx
[S14]: https://raw.githubusercontent.com/statico/smui/main/demo/src/components/ui/button.tsx
[S15]: https://raw.githubusercontent.com/statico/smui/main/demo/src/components/ui/tabs.tsx
[S16]: https://raw.githubusercontent.com/statico/smui/main/demo/src/components/ui/dialog.tsx
[S17]: https://raw.githubusercontent.com/statico/smui/main/demo/package.json
[S18]: https://raw.githubusercontent.com/statico/smui/main/demo/src/lib/utils.ts
[S19]: https://raw.githubusercontent.com/statico/smui/main/package.json
[S20]: https://raw.githubusercontent.com/statico/smui/main/LICENSE
[S21]: https://github.com/statico/smui/releases
[S22]: https://github.com/statico/smui
[S23]: https://github.com/statico/smui/commits/main/
[S24]: https://raw.githubusercontent.com/statico/smui/main/demo/public/skill.md
