# Paper Agent 迁移 SMUI 的成本评估

- 日期：2026-10-17
- 性质：静态源码调研与工程估算；不是实施决策，没有修改前端或安装主题。
- 上游事实与 URL 证据：[SMUI 官方调研](smui-theme-upstream.md)。以下工期均为推断，不是实测。

## 结论与估算

推荐保留 web_ui / Radix / React / Vite / Tailwind 4 和全部业务交互，在同一套现有语义 token 上应用 SMUI 视觉，不替换整套组件实现。

| 范围 | 单人有效工作量估算 | 完成含义 |
|---|---|---|
| 主题试样 | 0.5–1 人日 | 主要颜色、字体、token 圆角；不是全站验收完成 |
| 可交付的全站主题迁移（推荐） | 3–5 人日 | 所有已启用页面深浅模式、固定样式修正、中文排版与交互状态、自动化及浏览器回归 |
| 高保真终端风格 | 5–8 人日 | 在上述基础上统一字号、字距、密度、分隔、阴影、标签及组件 variants，不含信息架构重做 |

按 1 人日约 6–8 小时有效工程时间理解。假设现有功能可运行、验收环境可用，不含无关测试故障、后端或业务结构变更。推荐范围预计涉及约 15–30 个文件，属于规划区间，不是已算出的变更清单。若额外增加手动 light/dark/system 选择，在现有跟随系统方案之上另预留 0.5–1 人日；偏好跨设备同步不包含在该增量内。

## 当前代码证据

| 已验证事实 | 项目来源 |
|---|---|
| React 19、Vite 7、Tailwind 4、Radix；已安装 next-themes，但不能据此认为应用正在用其 Provider | `frontend/package.json`、`frontend/src/main.tsx` |
| 实际样式入口为 `./upstream/index.css`；不是 `frontend/src/index.css` | `frontend/src/main.tsx:14` |
| 应用 ThemeProvider 只监听系统配色并切换 html.dark；无手动主题、无持久化；首帧脚本也按系统配色设置类 | `frontend/src/lib/theme/theme-provider.tsx`、`frontend/index.html` |
| 当前同时有媒体查询驱动的旧色与 .dark 驱动的 shadcn 色；自定义文字、surface、shadow 中还有固定浅色值 | `frontend/src/upstream/index.css:24–235` |
| 导航条通过独立 app-rail-background 改写 sidebar 背景，标准 sidebar token 不是唯一入口 | `frontend/src/upstream/components/layout/AppSidebar.tsx:29` |
| 聊天输入、确认卡存在固定 22/26px 圆角，局部有 bg-white；只设置 radius=0 不足以全站零圆角 | `frontend/src/upstream/components/chat/ChatContent.tsx`、`TextInput.tsx`、`ConfirmCard.tsx`、`SubagentHitlCard.tsx` |
| 有两套 UI 源码，同名 Button 的 variants、size、tooltip API 不同；不宜直接覆盖为 SMUI demo 组件 | `frontend/src/components/ui/button.tsx`、`frontend/src/upstream/components/ui/button.tsx` |
| Markdown 使用 Streamdown 与 code/math/cjk/mermaid 插件，应验收实际渲染，不只验收页面背景 | `frontend/src/upstream/components/markdown/index.tsx` |
| PDF canvas 与纸张固定白色，引用为 amber 覆盖层；白纸属于原文内容，不应机械替换成深色背景或反色 | `frontend/src/components/papers/pdf-viewer.tsx:307–313`；保留白纸是本报告建议 |
| 当前路由覆盖登录、注册、文献库、发现、阅读、会话、定时任务、模型设置；上游残留页面不能当作全部上线范围 | `frontend/src/upstream/App.tsx` |
| shadcn 配置仍写 new-york，而项目决策要求跟随 web_ui radix-nova；不能凭 components.json 一键重装并认为无差异 | `frontend/components.json`、`docs/decisions/0014-frontend-on-web-ui.md` |

## 静态扫描规模（不是修改数量）

扫描 `frontend/src` 下非 test/spec 的 TS/TSX/CSS：293 个文件，其中 TSX 207 个。

- 固定色 utility 候选：19 个文件、65 处。
- arbitrary color utility 候选：2 个文件、8 处。
- dark: 候选：33 个文件、117 处。
- rounded 候选：116 个文件、325 处。

统计包括两套 UI 源码、未启用上游页面、合理的遮罩和 PDF 白纸；dark: 与 rounded 本身也不代表缺陷。它们是审计上界，不能作为必须改 116 个文件的依据。实施时应按当前路由与引用链筛选。

## 成本主要来源

1. **token 接入与双模式统一**：沿用现有完整颜色值消费者，将 SMUI 裸 HSL 包装为完整颜色，映射 sidebar-background → sidebar；补齐 canvas、导航、文字层级、状态色、引用色和阴影。官方线上 registry 当前 light/dark 相同，必须选定经核验的源码基准；详见上游报告。
2. **组件外观补齐**：标准 token 能覆盖大部分基础控件；固定像素圆角、白底、任意色与原有透明背景需要定向修正。不要全局 * 清空圆角或给所有白底染色。
3. **中文与长内容**：JetBrains Mono 的官方示例未给中文方案；建议导航/操作区借鉴等宽气质，中文正文保留可读 fallback，不照搬所有 11px 标签。字体变化需检查长论文标题、表格、弹窗按钮及引用块换行。
4. **真实状态回归**：hover、active、focus、disabled、selected、失败/成功/处理中、弹窗和菜单 portal、toast、流式消息、HITL、问卷、引用、代码高亮、公式和 Mermaid 都要覆盖深浅模式。

推荐范围工作量分配：token 与主题 0.5–1 人日；基础组件与壳层 0.5–1 人日；业务页面和消息内容 1–1.5 人日；双模式浏览器/自动化回归 1–1.5 人日。合计约 3–5 人日，不额外重复计算验证时间。

## 约束与推荐路径

- 不迁移 Next.js，不做 Radix → Base，不替换 SSE、消息滚动、工具调用、HITL、业务 API 或数据模型。
- 先在同一组语义 token 中做全局主题，不并列引入第二套 UI 库或把 demo 整体搬入。
- 保持当前跟随系统已经能够满足“适配深浅主题”；手动主题切换是另一项产品选择，不默认扩大范围。
- 修改视觉前需批准 design；0033 明确以 web_ui 视觉为底座，0055 明确圆角浮层。若采用全站 SMUI 零圆角，应更新相应决策的视觉约束，保留组件与交互复用原则。当前仅调研，不修改决策。
- 无需引入新的运行时主题框架；若严格复刻字体，可能增加字体资源或本地字体包，具体方案实施时再定。若采用 SMUI 自定义字号与 cn 合并，还需适配 tailwind-merge；仅配色不需要。

## 验收边界与未验证事项

已完成官方源码/registry 对照和本仓库入口、路由、样式及代表组件检查。未安装 SMUI，未启动浏览器、跑对比度计算、截图或迁移试验，因此估算不是高保真视觉承诺，也没有声明官方浅色已通过 WCAG。

实施验收应在系统 light/dark 下覆盖当前全部启用页面，校验启动无闪烁、系统切换同步、浮层与消息内容、原文白纸与引用可见性、窄视口和中文长标题；保持现有业务行为。按仓库要求运行后端 pytest 及前端 typecheck/test/build，并明确区分既有失败与本次引入问题。
