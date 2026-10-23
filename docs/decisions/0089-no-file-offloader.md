# 0089 — 关闭文件 offloader 与工作区提示词

- DATE: 2026-10-24
- TAGS: agent, security
- STATUS: 当前
- SUPERSEDES: 0068 中暂不替换工作区 manager 的片段；0010 的内建压缩要求保持

## DECISION

- `PaperAgent` 在框架装配边界强制 `offloader=None`，即使运行时传入 workspace 也不启用。继续使用 AgentScope 原生 ContextConfig 压缩与工具结果截断，不自建摘要机制。
- 不向系统提示词注入框架的文件目录、工作区、skills、scratch、uv/git 操作说明；无文件工具的白名单保持不变。
- 保留框架必需的 workspace 绑定，但它只返回空 instructions/tools/skills/MCPs，不创建目录、不提供 backend，不伪造 offload 文件路径。
- manager 缓存包含用户、Agent、Session 和 workspace ID。缺 ID 时由基类按 PER_SESSION 分配并缓存，返回前初始化；关闭时显式关闭对象，清除缓存；再次读取可重建。已有 Session 绑定 ID 不迁移。
- 回归测试直接调用框架压缩及超长工具执行路径，仅模拟模型响应，验证生成摘要和截断结果且无文件路径提示；另验证 owner/session 隔离与生命周期。

## REJECTED

- 只禁用文件工具但继续注入文件目录说明：模型会错误宣称具备文件读写能力。
- 将无 backend 的 workspace 当 offloader：长会话压缩与工具结果截断会运行时报错。
- 返回虚假的 offload 文件路径：掩盖错误并让模型依赖不存在的文件。
- 自己实现压缩或为了修复关闭内建压缩：违背 0010，长会话仍须可用。

## OUT OF SCOPE

文件工具、文件 artifact、Skill/MCP 市场、迁移已有会话、删除历史中旧的能力描述。
