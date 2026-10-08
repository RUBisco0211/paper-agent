# 0068 AgentScope workspace 不承载项目 artifact

- DATE: 2026-10-08
- TAGS: agent, product, storage
- STATUS: 当前
- SUPERSEDES: —

## DECISION

AgentScope 要求会话有 `workspace_id`，新会话由运行时按会话分配独立 ID；`cwd` 不作为产品概念或项目归属。未来项目 artifact 以业务 `project_id` 归属，内容进对象存储，业务数据记录元信息；`session_id` 可作来源记录，但 `workspace_id/cwd` 不能作授权、查询或存储键。已有会话的 workspace 绑定不迁移。

## REJECTED

不把项目映射为 AgentScope workspace，不把 artifact 存入 AgentScope 本地工作目录，也不把 `cwd` 暴露成项目设置。

## RATIONALE

本项目的范围与项目归属由业务库维护。AgentScope 的 `LocalWorkspaceManager` 即使分配不同 workspace ID，仍将同一 Agent 的实际本地目录指向同一路径；当前 PaperAgent 无文件工具，这个目录不承载业务数据。

## OUT OF SCOPE

实现 artifact 功能、定义全局会话 artifact 归属、迁移已有 workspace、替换 AgentScope workspace manager。

## OPEN

若以后开放文件工具，须在开放前实现物理工作目录隔离并重新审查权限边界。
