# 前端 UI 规范（必读）

适用范围：`frontend/` 下所有面向用户的界面。规则来源是 `@.agents/skills/shadcn/`（shadcn/ui 官方 skill）与产品反馈；与代码冲突时以本文为准。

## 1. 文案：只说用户需要知道的事

界面文案只有三种合法用途：

1. **当前状态**：正在做什么、结果是什么（"上传中…"、"处理完成"、"已停止"）。
2. **下一步动作**：按钮、链接、空状态的引导（"上传 PDF"、"去模型设置"）。
3. **后果确认**：用户做不可逆操作前需要判断的信息（"删除项目会同时删除项目会话，论文库不受影响"）。

以下内容**一律不出现在界面**（包括 header、图标下方、卡片、Sheet/Dialog 描述、Alert、Toast）：

| 禁止内容 | 曾经出现的反例 |
|---|---|
| 实现细节与部署方式 | "Base URL 由后端部署配置固定"、"后端地址：…" |
| 数据流向与隐私机制说明 | "PDF 会发往 MinerU，Chunk 会发往 Embedding 服务" |
| 内部存储位置与安全权衡 | "API Key 保存在浏览器 localStorage…不写入数据库、日志或对象存储" |
| 设计意图、架构术语、验收口径 | "OpenAPI → SSE → 事件游标"、"个人全库会话覆盖整个论文库；项目会话只覆盖该项目论文，范围创建后不可修改" |
| 面向开发者/测试的说明 | "处理中可查看阶段状态"、"该条目不参与全文检索" |
| 页面副标题与品牌口号 | 每个页头下方的 caption、"论文证据问答" |

判定方法：这句话是否帮助一个**只关心自己论文和问答结果**的用户完成当前任务？不是就删掉。删除后如果界面显得空，用更好的布局解决，不要用解释性文字填充。

**按钮文案**：用名词/动词短语，不用口语（"重命名"而不是"改名"，"提问"而不是"就用这篇提问"）。同一动作在全站用同一个词。

**占位符（placeholder）**：只用于两种情况——格式示例（`sk-…`、`10.1145/3290605.3300233`）或选择提示（"选择项目"）。不要用口语化描述（"按标题过滤""针对论文提问…"）；能用 `aria-label` 说明用途的输入框就不写 placeholder。

**例外**：错误提示必须给出稳定的、可行动的信息（例如"来源没有提供公开可用的 PDF，可手动上传"），这是状态而非机制说明。

### 1.1 不要为不存在的能力提供入口

界面不得出现规格未提供的能力入口（例如"从项目移除论文""删除论文"）。首版项目论文只增不减
（见 [minimal-mvp.md](../overview/minimal-mvp.md) F04 与 §5 的"无移除接口"），个人论文库也没有移除功能。
确实需要新增能力时，先改功能规格，再改后端，最后才加界面。

## 1.2 用语

| 用 | 不用 |
|---|---|
| 文献（文献库、单篇文献） | 论文、论文库、文档 |
| 全局（覆盖个人全部文献的会话范围） | 个人全库、全库、全部文献 |
| 重命名 | 改名、编辑名称 |
| 提问 / 新建会话 | 针对文献提问、就用这篇提问 |
| 引用原文 | 引用证据、证据片段 |
| 条目状态：可检索 / 处理中 / 处理失败 / 待补全文 | 能力、能力标签、关键词索引、向量索引 |

不要在界面上出现「能力」这类内部抽象，也不要把内部枚举（`upload`、`unrecognized`）、
内部 ID（citation id）或计数字段（尝试次数）暴露给用户：状态用一句话说清，细节放到详情面板。

## 2. 布局：侧边栏分上下两部分

参考 ChatGPT 的侧边栏结构：

- **上半部分**：通用导航（论文库、项目、模型设置），顶部只放产品名，不放副标题。
- **下半部分**：会话列表，**按项目分组**（"未分组"或个人全库在最前），每组可折叠，组内按创建时间倒序；提供"新建会话"入口。会话项的删除/改名放在该项的行内菜单或悬浮操作里。
- 折叠态由 `SidebarProvider` 管理，不在页面里手写开关状态。
- 主内容区使用 `SidebarInset`，页头只放标题与操作按钮，**不放描述文字**。

## 3. 组件：用 shadcn 组件，不手写等价物

来源：`.agents/skills/shadcn/SKILL.md` 与 `rules/*.md`。本项目为 `style=new-york`、`base=radix`、`tailwindVersion=v4`、`iconLibrary=lucide`。

- **安装方式**：一律用 CLI（`pnpm dlx shadcn@latest add <component>`）。若 CLI 因环境问题不可用，可安装到临时目录后用 `node_modules/.bin/shadcn` 运行；不要手工从 GitHub 抠文件。
- **图标**：只用 `lucide-react`；`Button`/`DropdownMenuItem`/`SidebarMenuButton` 等组件内的图标加 `data-icon="inline-start|inline-end"`，**不加 `size-4`**；图标以组件对象传入（`icon={CheckIcon}`），不用字符串查表。
- **空状态**用 `Empty`；**提示条**用 `Alert`；**加载占位**用 `Skeleton`；**状态标记**用 `Badge`；**分隔**用 `Separator`；**按钮的等待态**用 `Spinner`（`Button` 没有 `isLoading`）；**破坏性确认**用 `AlertDialog`。
- **表单**用 `FieldGroup` + `Field`（+ `FieldLabel`/`FieldDescription`/`FieldError`），校验用 `data-invalid` + `aria-invalid`；2–7 个选项用 `ToggleGroup`；带按钮的输入用 `InputGroup`。
- **菜单/下拉的条目必须在 Group 内**：`SelectItem` → `SelectGroup`，`DropdownMenuItem` → `DropdownMenuGroup`。
- **聊天**用 `MessageScroller*` / `Message*` / `Bubble*` / `Marker*`，不要手写气泡 `div` 与滚动容器；流式跟随、锚定、跳到最新由组件负责。生成中的"正在生成…"用 `shimmer` 工具类，不写自定义动画。
- **状态配色**：处理/阶段状态统一用语义 variant——**完成或成功 = `success`（绿）**、**失败 = `destructive`（红）**、**未完成/进行中 = `warning`（黄）**，未开始用 `outline`。不要用裸色值；不要在界面显示内部计数（如阶段尝试次数）或内部 ID（如 citation id）。
- **样式**：只用语义色（`bg-background`、`text-muted-foreground`、`text-success`、`text-warning`、`text-destructive`）；`className` 只用于排版布局；用 `gap-*` 而不是 `space-y-*`；等宽高用 `size-*`；省略用 `truncate`；条件类名用 `cn()`；不要在浮层组件上写 `z-index`。
- **可访问性**：`Dialog`/`Sheet`/`Drawer` 必须有 `DialogTitle`/`SheetTitle`（必要时 `sr-only`）；`Avatar` 必须有 `AvatarFallback`；`TabsTrigger` 必须在 `TabsList` 内。

## 4. 夜间模式

- **自动跟随系统**，不提供手动开关、不持久化偏好：`ThemeProvider` 监听 `prefers-color-scheme`，把 `.dark` 类挂到 `<html>`。
- `index.html` 里有一段首帧前的内联脚本，避免亮/暗闪烁；`<meta name="color-scheme" content="light dark">` 与 CSS 中的 `color-scheme` 让原生控件（滚动条、表单、PDF 查看器外观）跟随模式。
- 组件只用语义 token，禁止裸色值；新增颜色必须同时给出 `:root` 与 `.dark` 两套值。
- 第三方带主题的组件要显式跟随（例如 `Toaster` 使用 `theme="system"`）。
- PDF 原文由浏览器内置查看器渲染，不额外做暗色处理。

## 5. 动效

- **必须有动效的地方**：页面切换（内容区 `key` 变化 + `animate-page-in`）、侧边栏展开/收起（上游 `Sidebar` 自带宽度过渡）、Sheet/Dialog/Dropdown 开合（上游组件 + `tw-animate-css`）、折叠区展开（`CollapsibleContent` 用 `animate-collapsible-down/up`）、按钮与菜单的 hover/active 过渡。
- **强度**：入场 160–220ms、`cubic-bezier(0.22, 1, 0.36, 1)`；退场更快（≈160ms、ease-in）。只动 `opacity`/`transform`/`height`，不要动 `width` 之外的布局属性，也不要让内容跳动。
- **实现方式**：优先用组件自带动画；通用动画定义在 `src/index.css` 的 `@theme`（`--animate-*`）与 `@keyframes` 中，不在组件里写行内 style 动画。
- **可访问性**：`prefers-reduced-motion: reduce` 下所有动画时长压到 0.01ms（已在 `index.css` 全局处理）。
- **依赖**：`tw-animate-css` 提供 `animate-in/out`、`fade-in-0`、`zoom-in-95`、`slide-in-from-*` 等类，缺了它上游组件的动画会静默失效。

## 6. 本项目的前端约定

- **`cn` 来自上游 `cn` 包**（不是自建 `lib/utils.ts`）：`import { cn } from "cn"`。
- **主题工具类**在 `src/index.css` 中定义：`shimmer`、`scroll-fade`/`-x`/`-b`、`scrollbar-thin`、`scrollbar-gutter-stable`、`no-scrollbar`。上游聊天组件引用它们；不要删，也不要在组件里另写等价动画。
- **色板**统一使用 `oklch` 语义变量（含 `--sidebar-*`）；新增颜色请按同一格式加入 `:root` / `.dark` 与 `@theme inline`。
- **CLI 环境问题**：本机 Node 26 下 `pnpm dlx shadcn@latest` 会因 `@modelcontextprotocol/sdk` 需要 `zod/v4` 而崩溃。已在 `/tmp/shadcn-cli` 用 npm 安装 `shadcn` + `zod@^3.25` 作为替代运行时；`components.json` 的 aliases 使用相对路径（`src/components` 等），因为根 tsconfig 是 solution-style 没有 `paths`。
- **页面结构**：受保护页面渲染在 `AppShell`（`SidebarProvider` + `SidebarInset`）内，页头用 `PageHeader`（只有标题与操作）。

## 7. 校验

改动前端后至少执行：

```bash
cd frontend && pnpm run typecheck && pnpm run test && pnpm run build
```

新增交互（发送模式、排队提示、失败语义等）应补组件测试，断言的是**用户可见的语义**，而不是实现细节。
