# 0094 下载与文档处理分成两条记录，一次流程汇总在队列里

- DATE: 2026-10-26
- TAGS: data, ingest, product
- STATUS: 当前
- SUPERSEDES: 0092 的「记录模型」「四阶段含 source」「等待者名单」条款；0093 中 `paper_imports` / `import_stages` 两表的存废与 `user_papers.ready`

## DECISION

运行领取只消费 pending；有效 running 不重复领取。执行者在整个运行期间持有 PostgreSQL 排他 advisory lock 并定期续租，过期回收不得释放仍被执行者持有的 run。文献模型迁移不得删除会话或定时任务绑定；已执行的删除不由后续升级隐式伪造恢复。

**标识符获取与文档处理是两条记录。** `downloads` 记「某个用户请求为某个标识符取一份文件」，`runs` 记「一篇论文的一次处理」。两者都不再叫 import，`import_stages` 不再存在。

**`papers` 的身份唯一键保持 `file_hash`。** 论文只在文件到手后才存在，因此不会出现「有 DOI 没文件」的行。下载成功后算 hash，命中则复用并补齐 `doi` / `arxiv_id`，未命中则用该 hash 建行。

**`downloads` 按用户建行，不对标识符或 URL 做全局唯一。** 同一 URL 可能下到不同文件（版本更新、镜像、重定向），只有 hash 才能判定是否同一文件。列：`user_id`、`identifier_type`、`identifier`、`status`、`paper_id`、`run_id`、`source_url`、`error_message`、时间戳。终态不再改写；重试即新建一行。

**下载异步执行。** 提交只写一行 `downloads` 并返回，由 worker 领取执行。批量入库因此是 N 次独立提交，不需要批量接口，也不需要模态等待。

**`runs` 绑定一篇已存在的论文，一篇论文最多一条进行中。** 列：`paper_id`、`status`（`pending` / `running` / `success` / `failed`）、`current_stage`（`parse` / `chunk` / `embed`，全部完成时为空）、`stage_timings`（JSONB，各阶段起止时间）、`error_message`、`leased_until`、`started_at`、`finished_at`。部分唯一索引：`(paper_id) WHERE status IN ('pending','running')`。

**挂靠判定同时覆盖 `pending` 与 `running`。** 上传与下载成功两条入口在此汇合：按 `paper_id` 查进行中的 run，有则只写 `user_runs`，无则建 run 并写 `user_runs`；`downloads.run_id` 回填为接入的那条 run。遗漏 `pending` 会撞上述唯一索引。

**`user_runs` 记谁请求过这次处理，`user_papers` 只记谁拥有这篇。** `user_papers` 在该用户参与的 run 成功时写入，`ready` 与 `source` 两列删除：行存在即可用，进度由 `downloads` / `runs` 承担。

**崩溃由租约收回。** worker 领取时写租约截止时间并定期续租；别的 worker 发现过期即判该 run 失败，`current_stage` 保持原值，`error_message` 记处理中断。与正常失败走同一出口。

**界面只有一个队列。** 以 `downloads` 为行，前端把成功的下载与它接入的 run 串成一次流程；下载自身失败与该 run 失败分别标注，下载失败的行不显示后续阶段。

## REJECTED

- 在请求内同步下载：批量提交时单个失败留不下记录，且请求被慢下载占住。
- 对同一标识符或 URL 做全局唯一：无法据 URL 判断两份文件是否相同。
- 提前用标识符建 `papers` 行、下载后回填 `file_hash`：与「用户上传同一文件但读不出标识符」产生的行冲突，出现两行同一篇论文。
- 保留独立阶段表：阶段数固定为三个，只用于排查，不需要索引；并入 `current_stage` 与 `stage_timings`。
- 保留 `user_papers.ready`：现在不存在「条目已建但不可用」的中间态。
- 由一个共享导入记录承载所有用户的进度：某用户的失败会被别人的重试改写。
- 界面拆成下载与处理两个队列：分层属于数据侧，用户只关心「我提交的东西怎么样了」。

## RATIONALE

「获取标识符对应的文件」与「处理一篇论文」的目标对象不同：前者面对标识符，可能一无所获；后者面对已知文件，必有结果。压成一条记录就必须让论文在处理开始前凭空存在，进而引发按标识符建行与按 hash 建行的冲突。拆开后 `papers` 只在文件到手时出现，`run` 永远绑定真实存在的论文，判断条件全部退化为单表事实。

## OUT OF SCOPE

租约超时时长与失效判定的调优；同一标识符被多人提交时的下载复用；按解析器版本重解析。

## OPEN

无。
