# 0003 业务服务为模块化单体，业务包固定七文件分层

- DATE: 2026-09-24
- TAGS: arch
- STATUS: 部分有效 —— 业务包分层仍适用，agent / 会话层已被 0006 取代
- SUPERSEDES: —

## DECISION

业务服务是模块化单体。每个 Router 业务包固定 `api / schemas / depends / service / domain / repo / ports` 七文件，依赖方向 `api → service → domain / repo / ports → platform`，反向一律禁止。支持包（`processing`、`embedding`、`evidence`、`scholar`、`platform`）按能力划分，不按业务包复制结构。**范围**：0006 移交的只是 agent 执行、会话与事件总线；业务包（library / projects / ingestion / retrieval / imports / auth）仍照此分层 —— 该规则现落在 `AGENTS.md` 第 2 节（目录职责与七文件）与第 5 节（依赖方向禁令）。

## REJECTED

- 引入完整仓储抽象或 Unit of Work：跨业务包协作是单体内明确的引用关系，加一层抽象只会增加转发代码。
- 把业务服务拆成可独立部署的多个服务：当前规模是单机单进程。0012 的解析 worker 是作业进程（共享同一业务库），不是服务拆分。
- 给支持包补齐 Router、repo 或转发类以"统一外观"：纯计算保留为函数，有状态或有外部交互的用类。
- 保留旧模块路径兼容壳：`dependencies / application / persistence` 一次性迁移，代码、测试、入口统一引用新路径。

## RATIONALE

分层靠 `backend/tests/test_architecture.py` 做结构检查（业务包文件结构、执行代码不反向引用 HTTP 装配、Router 不直连仓储），比口头约定可判定。

## OUT OF SCOPE

Redis、Celery、多实例协调。

## OPEN

重构后该结构检查是否需要覆盖 `extra_agent_tools` 的注入点。
