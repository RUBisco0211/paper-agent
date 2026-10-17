# SMUI 主题迁移验收记录

- 日期：2026-10-17；Issue：[#1](https://github.com/RUBisco0211/paper-agent/issues/1)；分支：`feature/smui-theme`。
- 结论：主题迁移与本轮适用验证已完成，等待用户 review / 合并；不表示真实 LLM 全链路重新验收通过。
- 主题依据：[0080](../decisions/0080-smui-theme.md)；官方配色来源：[SMUI src/globals.css，固定版本 b917de0](https://github.com/statico/smui/blob/b917de0283e3edc8d1689083d02e29eef2acb1bf/src/globals.css)、[官方 skill](https://smui.statico.io/skill.md)。

## 自动验证

| 命令 / 检查 | 实际结果 |
|---|---|
| `docker compose up -d postgres` | PostgreSQL 正常运行；本轮先启动本机 OrbStack |
| `cd backend && uv run pytest -q` | 240 passed，1 skipped，0 failed；真实 PostgreSQL，148.30 秒 |
| `cd frontend && pnpm run typecheck` | 通过 |
| `cd frontend && pnpm run test` | 48 文件、204 测试通过；迁移前基线为 42 文件、144 测试 |
| `cd frontend && pnpm run build` | 通过 |
| `cd frontend && pnpm install --frozen-lockfile --offline --ignore-scripts` | 通过；锁文件仅增加 JetBrains Mono，无无关依赖升级 |
| `git diff --check` | 通过 |

新增主题、基础组件、业务外观和 PDF 样式契约先红后绿；独立复核补充发现的状态叠色问题也先用新测试复现，再修正语义色。对比度检查包含 48 组「双模式 × 四状态色 × background/card × 10/15/20% 叠色」，不以纯背景测试代替实际徽章表面。

## 浏览器验证

Playwright Chromium；本地 Vite + 业务服务 + AgentScope 服务 + PostgreSQL；1440×960 桌面与 390×844 窄屏，通过模拟系统配色驱动既有 ThemeProvider，无手动主题入口。

- 真实后端：注册、文献库、在线检索入口、会话草稿、定时任务、模型设置、导入弹窗；检查 `.dark`、`color-scheme`、实际字体、按钮与浮层方角、无整页横向溢出。
- 真实后端：上传一页合成 PDF 并打开阅读页；两模式下纸张与 canvas 均保持白色，外壳随主题变化。此处只验证原文显示；解析产物是否已就绪随本地后台处理状态而定，不计入解析质量验收。
- 合成组件样例：复用生产消息渲染器，覆盖表格、代码、KaTeX、Mermaid、状态徽章、错误提示和问卷选择/提交；未伪装成真实模型返回。Mermaid 同一 SVG 连线随模式由 `rgb(59,67,84)` 变为 `rgb(153,165,178)`，不依赖重建会话。
- 窄屏：使用已有「收起会话侧栏」操作后检查输入与换行；侧栏仍默认展开，本轮未改变布局行为。
- 上述最后一轮浏览器运行没有 `pageerror`。临时组件样例文件已移除，辅助脚本及原图留在忽略的 `.var/smui-qa/`，不会随项目上传。

## 截图

以下拼图每格标明真实后端页面或合成组件样例，均为本轮测试数据，无个人文献或凭据。

- [浅色预览](smui-theme-light.png)
- [深色预览](smui-theme-dark.png)

## 边界与风险

- 未使用真实 LLM Provider，未重复验证模型流式输出、真实工具调用与 HITL 的端到端执行；既有相关自动回归通过，问卷交互另用真实组件样例验证。
- 未做全站 WCAG 认证或所有 Mermaid 图种的视觉遍历；新增测试只保证列明 token 组合，图形浏览器样例为 flowchart。
- 窄屏在会话侧栏展开时内容区仍会很窄，这是保留的现有布局限制；不借主题迁移重做响应式导航。
- 现有大 chunk、Node localStorage 实验性提示等警告不阻断构建/测试；本轮不处理无关依赖与打包重构。
- 本地 shadcn docs CLI 因既有 `zod/v3` 导出兼容错误不可用，已读取官方组件文档及 SMUI skill；未为此升级整套依赖。

## 同一 PR 的全局样式抽取补充验收

- 第一、第二批已落实：主题、控件密度、状态表面、浮层、Tabs、导航与工具栏、会话内容宽度、输入和工具预览、动效均在全局 CSS 分模块维护，配有中文说明。
- 组件保留结构、语义 class、variant/size 与运行时定位；被接管的数值和局部 dark 配色已移除。输入框壳、引用浮层和状态徽章不再由调用点拼装重复视觉规则。
- 本次没有新增测试文件或用例；按用户确认同步两个既有样式测试文件，当前仍为 **48 文件、204 测试通过**；typecheck/build 通过，后端重新运行 **240 passed、1 skipped（148.30 秒）**。
- 双模式浏览器覆盖检查：全局控件高度改为 40px、导航改为 72px、工具栏改为 60px 后实际尺寸一致；字体、18px 正文字号、8px 圆角、5px 焦点环和控件背景均按根变量生效。
- Dialog padding 改为 24px 后，content/footer 留白均为 24px，footer 负 margin 为 -24px，没有残留 16px 覆盖。
- Composer 默认行高 21px、最小高度 52px；覆盖为 24px/64px、横向留白 20px 后，ghost 与 textarea 均同步，按钮行高 64px，上限为 **184px**；长文本实际高度 184px、scrollHeight 400px，正确滚动。按钮占位和真实按钮随同一高度变量由 36px 变为 40px。
- 独立复核发现 components 层行高被 text-sm utility 覆盖，已移除相应覆盖并复核关闭；没有使用 !important。减少动态效果下，控件过渡实际为 0s。
- 最后一轮双模式页面与组件检查均无 pageerror；截图已刷新为最新实现。验证使用独立 Vite 5175/API 18000 端口和临时 QA origin，未重启或停止用户已有 5173/8000/8001 服务，未更改生产跨域配置。
- 未新增依赖；本次仍未重新联调真实 LLM 全链路。临时浏览器样例已删除，本地辅助文件仍仅保留于忽略的 .var/smui-qa。
