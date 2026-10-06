# 0007 一个 PostgreSQL 实例、两个 database

- DATE: 2026-10-05
- TAGS: data, infra
- STATUS: 当前
- SUPERSEDES: —

## DECISION

agentscope 的 13 张表放独立 database，业务表放另一个 database，同一 PG 实例。Storage 用 `AsyncSQLAlchemyStorage`，MessageBus 用 `InMemoryMessageBus`。跨边界不做 DB JOIN：业务侧建 `session_binding(session_id, user_id, project_id, scope)`，在应用层用 `session_id` 拼接。Redis 不引入；将来若引入只作缓存，不作持久化。

## REJECTED

- 一个 database 两个 schema：能跨 schema JOIN，但两套 Alembic 迁移历史要各自隔离 `version_table`，权限只能靠 grant。
- 两个 PG 实例 / 容器：故障域也隔离，但 compose 多一个服务、备份与监控两套。
- 共用 public 并改业务表名避开冲突：一个库一个 schema，代价是整个 ER 图改名。
- `RedisStorage` / `RedisMessageBus`：MessageBus 不是持久化层，只是会话锁、replay 与 inbox 的运行时通道，多实例才需要 Redis。

## RATIONALE

它的表没有前缀（`sessions` / `messages` / `agents` …），与业务 ER 图同名，必须隔离。不能跨库 JOIN 反而是好处：强制业务代码不直接依赖框架的表结构，框架升级改 schema 时业务侧不受影响。

## OUT OF SCOPE

跨库 JOIN、postgres_fdw、读写分离、Redis 持久化。

## OPEN

两个库的备份策略是否分开；`auto_migrate=False` 时业务侧如何承接它的 Alembic 迁移。
