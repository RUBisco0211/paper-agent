# 0003 业务服务为模块化单体，业务包固定七文件分层

- DATE: 2026-09-24
- TAGS: arch
- STATUS: 当前 —— 仅约束业务包；AgentScope 服务边界见 0006
- SUPERSEDES: —

## DECISION

业务服务是模块化单体。每个 Router 业务包固定 `api / schemas / depends / service / domain / repo / ports` 七文件，依赖方向 `api → service → domain / repo / ports → platform`，反向一律禁止。文献流程归于 `library / imports / processing / retrieval` 四个业务包；PDF/MinerU、学术来源、向量适配与证据纯逻辑集中在 `literature_support/`，按能力划分，不为统一外观补 Router。0006 移交的只是 agent 执行、会话与事件总线；业务包仍照此分层。

## REJECTED

- 引入完整仓储抽象或 Unit of Work：跨业务包协作是单体内明确的引用关系，加一层抽象只会增加转发代码。
- 把业务服务拆成可独立部署的多个服务：当前规模是单机部署。0056 的解析 worker 是作业进程（共享同一业务库），不是服务拆分。
- 给支持包补齐 Router、repo 或转发类以"统一外观"：纯计算保留为函数，有状态或有外部交互的用类。
- 保留旧模块路径兼容壳：`dependencies / application / persistence` 一次性迁移，代码、测试、入口统一引用新路径。

## RATIONALE

分层靠 `backend/tests/test_architecture.py` 做结构检查（业务包文件结构、执行代码不反向引用 HTTP 装配、Router 不直连仓储），比口头约定可判定。

## OUT OF SCOPE

Redis、Celery、多实例协调。

## OPEN

重构后该结构检查是否需要覆盖 `extra_agent_tools` 的注入点。
