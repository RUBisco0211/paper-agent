# SMUI 主题迁移验收记录

- 日期：2026-10-17；Issue：[#1](https://github.com/RUBisco0211/paper-agent/issues/1)；分支：`feature/smui-theme`。
- 结论：主题迁移与本轮适用验证已完成，等待用户 review / 合并；不表示真实 LLM 全链路重新验收通过。
- 主题依据：[0080](../decisions/0080-smui-theme.md)；官方配色来源：[SMUI src/globals.css，固定版本 b917de0](https://github.com/statico/smui/blob/b917de0283e3edc8d1689083d02e29eef2acb1bf/src/globals.css)、[官方 skill](https://smui.statico.io/skill.md)。

## 自动验证

| 命令 / 检查 | 实际结果 |
|---|---|
| `docker compose up -d postgres` | PostgreSQL 正常运行；本轮先启动本机 OrbStack |
| `cd backend && uv run pytest -q` | 240 passed，1 skipped，0 failed；真实 PostgreSQL，146.15 秒 |
| `cd frontend && pnpm run typecheck` | 通过 |
| `cd frontend && pnpm run test` | 48 文件、204 测试通过；迁移前基线为 42 文件、144 测试 |
| `cd frontend && pnpm run build` | 通过 |
| `cd frontend && pnpm install --frozen-lockfile --offline --ignore-scripts` | 通过；锁文件仅增加 JetBrains Mono，无无关依赖升级 |
| `git diff --check` | 通过 |

新增主题、基础组件、业务外观和 PDF 样式契约先红后绿；独立复核补充发现的状态叠色问题也先用新测试复现，再修正语义色。对比度检查包含 48 组「双模式 × 四状态色 × background/card × 10/15/20% 叠色」，不以纯背景测试代替实际徽章表面。

## 浏览器验证

Playwright Chromium；本地 Vite + 业务服务 + AgentScope 服务 + PostgreSQL；1440×960 桌面与 390×844 窄屏，通过模拟系统配色驱动既有 ThemeProvider，无手动主题入口。

- 真实后端：注册、文献库、在线检索入口、会话草稿、定时任务、模型设置、导入弹窗；检查 `.dark`、`color-scheme`、实际字体、按钮与浮层方角、无整页横向溢出。
- 真实后端：上传一页合成 PDF 并打开阅读页；两模式下纸张与 canvas 均保持白色，外壳随主题变化。没有调用 MinerU，右栏保留「尚未完成解析」状态。
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
