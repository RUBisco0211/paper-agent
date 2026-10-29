# 0096 阶段级并发与失败退避

- DATE: 2026-10-27
- TAGS: ingest, data, arch
- STATUS: 当前
- SUPERSEDES: 0094 中「一个 run 由一个执行者跑完全部阶段」的表述

## DECISION

**领取粒度从一个 run 改为一个阶段。** 执行者只领取 `current_stage` 指向的那一个阶段，跑完提交后归还线程，下一个阶段再被独立领取。下载、解析、切块、向量化各自有独立的并发上限，互不占用对方的槽位。

**`current_stage` 从展示字段变成调度状态。** `status=pending` 时它表示「下一个可被领取的阶段」，`running` 时表示「正在执行的阶段」。阶段成功推进时若已无后续阶段，`status=success` 且 `current_stage` 置空。

**每个阶段独立计失败次数。** `runs` 增加 `stage_attempts`（JSONB，形如 `{"parse": 2}`）。阶段失败时自增，未达上限则 `status` 回到 `pending`、`current_stage` 不变，等待退避到期后自动重试；达到上限则 `status=failed`，保留最后一次错误。

**退避时间存 `runs.next_attempt_at`。** 只描述当前阶段。阶段推进到下一阶段时清空；阶段失败未达上限时写入。领取查询要求该字段为空，退避中的行不进入可领取集合。

**退避计算抽成独立的纯函数**，基数与上限作为参数传入。邮件投递沿用其既有的 15 秒基数与 600 秒上限；阶段重试使用 60 秒基数与 300 秒上限，最多 3 次尝试。

**用户手动重试即新建 run**，新 run 的阶段计数与退避自然归零，不需要额外的清零逻辑。

**索引只覆盖现在就能跑的行。**

```sql
CREATE INDEX ix_runs_stage_queue
ON runs (current_stage, created_at)
WHERE status = 'pending' AND next_attempt_at IS NULL;
```

`ix_runs_status` 在阶段级领取后不再被使用，删除。

**同一 run 仍必须只有一个执行者。** 阶段级领取时以 advisory lock 锁住 `run_id`，覆盖「执行一个阶段」的生命周期，跑完释放。锁不再跨越整个 run。

## REJECTED

- 保持整篇处理、只给各阶段加信号量：慢阶段会长期占住线程，需要把线程池开到各阶段之和，资源占用反而上升。
- 把 `stage_attempts` 存 Redis：它必须与 `status`、`current_stage` 的迁移同一事务，跨库无法保证一致；Redis 重启后次数归零会让必然失败的任务无限重试。
- 无限自动重试：必然失败的任务会持续消耗 MinerU 配额与向量额度。
- 阶段失败立即判整条 run 失败：限流类错误本可在下一次尝试中成功。

## RATIONALE

四个阶段的瓶颈不同——网络、MinerU 日配额、本机 CPU、向量 token——用一个数字同时约束它们，最紧张的那个会决定全局速度。按阶段领取让每类资源各自跑满，又不必把线程池撑大。重试次数与退避放进 `runs`，是因为它们和状态迁移必须原子。

## OUT OF SCOPE

按阶段分队列以支持跨机器分布式 worker；任务优先级。

## OPEN

无。
