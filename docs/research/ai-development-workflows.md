# AI 辅助开发的规范与进度管理

- DATE: 2026-09-21（本次改写仅压缩结构，未更新结论）
- STATUS: 当前

调研时为研究与建议，未安装涉及的工具。**本文件的大部分建议已被 `AGENTS.md` / `WORKFLOW.md` / `docs/DECISIONS.md` 吸收落地**，保留作为背景依据。

## 结论

采用「**增量规格 + 可执行约束 + 有证据的验收**」：聊天是提出意图的入口，仓库是长期记录，运行结果是完成依据。保留现有 F01–F09，先补齐规范之间的权威关系、CI 与真实用户流程验证，**再决定要不要装 OpenSpec**。

单一记录位置的分工（现行分工见 `AGENTS.md` 第 12 节）：

| 问题 | 唯一记录位置 |
|---|---|
| 为谁解决什么、当前交付边界 | `docs/decisions/0018`–`0031`（功能范围已拆为决策条目） |
| 领域术语 | `docs/decisions/0034` |
| 模块、依赖方向、部署限制 | `AGENTS.md` 第 2 节与 `docs/decisions/0006`–`0013` |
| 为什么选当前方案 | `docs/decisions/NNNN-*.md` |
| 这次改什么、做到哪 | 一份活动变更记录 |
| 哪些已实现、已验收、被阻塞 | `AGENTS.md` 第 9 节 + 实际代码（不再单独成文） |
| 以前考虑过什么 | 决策条目的 REJECTED 字段 |

## 依据

| 范式 | 事实 | 对 Paper Agent 的判断 |
|---|---|---|
| GitHub Spec Kit | constitution + 需求/计划/任务/对照检查 | 适合较大新能力；当前不必重新生成一整套平行文档 |
| OpenSpec | 分开当前 specs 与拟议 changes，proposal/design/tasks/delta | 最贴合现有 MVP：每次只明确改变哪些已存在的行为。可先用 Markdown 试行，装 CLI 前必须把现有规格映射过去，避免两个权威副本 |
| Harness engineering | 短 AGENTS 做导航，知识与计划留在仓库，靠 lint/结构检查/可观测环境约束 Agent | 优先借鉴可重复启动、自动检查、依赖边界、可复现错误。其高吞吐是特定团队实验，不是降低门禁的证据 |
| 长任务交接 | 初始化环境 + 功能清单 + 进展文件 + Git 记录 | 用一份活动任务记录保存验收项、已做工作、证据与下一步 |
| 小批次持续集成 | GitHub flow、DORA 小批量短命分支 | 一个变更解决一个可观察问题，主分支持续可运行 |
| ADR | 短文记上下文/决策/状态/后果，被替代时保留历史 | 用于「为什么进程内调度」「为什么 Session 范围存 Entry」这类长期约束 |

材料只证明方法与工具存在，不能据此断言某工具一定提高本仓库质量；规格的结构校验不能替代实现行为验收。

## 备选方案与取舍

- **优先把已有命令变成门禁**（`pnpm run typecheck/test/build`、真实 PostgreSQL 后端测试）进 CI，再谈新工具。
- **值得写成边界检查的只有五类**：会话范围由服务器决定（跨账号/跨项目/伪造引用）、外部 SDK 差异留在适配接口内、输入与外部响应在边界校验且失败阶段不标成功、前端消费统一 API 契约、高风险状态变化用行为测试保护（停止/续跑、pending 投递、SSE 重连、解析重试幂等）。
- **进度按验收能力报告**：实现状态（未开始/进行中/已合入）与验证状态（未验证/自动化通过/真实集成通过/浏览器验收通过）分开记，附阻塞原因与证据（命令、结果、环境、commit，不写 API Key）。「F06 已实现」可以同时「真实模型浏览器闭环待验收」。完成百分比没有稳定分母时会误导。
- **评测**：对术语查询、语义查询、跨文献、无证据、服务故障建固定样例，分别评证据是否授权、引用是否可展开、答案是否被证据支持；模型输出可变，不用逐字匹配当质量标准。

## 参考

- [OpenSpec 概念](https://github.com/Fission-AI/OpenSpec/blob/main/docs/concepts.md) · [GitHub Spec Kit](https://github.com/github/spec-kit)
- [OpenAI harness engineering](https://openai.com/index/harness-engineering/) · [Anthropic 长任务 harness](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Anthropic evals 指南](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [Documenting architecture decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) · [DORA](https://dora.dev/guides/dora-metrics/)
