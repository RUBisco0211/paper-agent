# 0093 表字段精简、产物路径扁平化与错误文案归属

- DATE: 2026-10-25
- TAGS: data, ingest, storage, frontend
- STATUS: 当前
- SUPERSEDES: 0056 的「MinerU 产物按 job 版本目录存放」条款；0091 中 `user_papers.source` 相关表述

## DECISION

**`user_papers` 只表达「谁收藏了哪篇」。** 删除 `source` 列与 `PaperSource` 枚举：一次导入从哪来属于导入行为，已由 `paper_imports.identifier_type` 记录，不属于这条收藏关系。

**MinerU 产物不再按 job 分子目录。** 产物写在 `mineru/{hh}/{hh}/{file_hash}/` 下，同名文件覆盖；`manifest.json` 最后写入，写完才更新 `papers.artifact_manifest_key`。解析前不删除旧产物。

**产物是否可用由解析阶段入口判定，判定不通过即重新解析。** `papers.artifact_manifest_key` 有值只是必要条件：进入解析阶段时按该 manifest 逐个文件重算 sha256，全部相符才跳过；任何一个不符（含解析中途失败留下的半截文件）都视为该阶段未完成，重新执行解析并覆盖写入新产物与新 manifest。校验不通过本身不报错，只有重新解析也失败才记为该阶段失败。切块阶段因此不再自行校验产物。

**Chunk 不再复制产物指针。** 切块整篇替换，`chunk_metadata.artifact_manifest_key` 恒等于论文上的指针，副本删除。

**错误文案只由后端提供。** 删除 `import_stages.attempt`、`import_stages.progress` 与 `paper_imports.error_code`；保留 `import_stages.error_message`，前端直接显示它，删除前端的错误码到文案映射表。文案沿用各错误抛出点现有的 `message`，parse 阶段直接透传 MinerU 返回的 `err_msg`，不建立「错误码 → 文案」映射表。

**保留**（逐条确认过，有读取方或已明确的预留用途）：`papers.byte_size`、`page_count`、`mineru_version`、`metadata_sources`、`updated_at`；`paper_imports.status`（worker 领任务的索引）、`started_at`/`finished_at`；`import_stages.started_at`/`finished_at`。**删除 `MetadataStatus` 枚举与 `ProviderMetadata.metadata_status()`**，二者已无调用方。

## REJECTED

- 按 `{mineru_version}/` 给产物分版本目录：版本号来自 MinerU 返回包内的 `version.json`，解析结束才知道，而路径必须在写产物前确定。
- 保留 `runs/{job_id}/`：没有「解析成功后再重新解析」的入口，该目录只带来无人清理的堆积。
- 解析前清空整个产物前缀：中途失败会让指针悬空，`has_parsed` 误判为真。
- 由切块阶段校验产物并报 `import_artifact_invalid`：解析阶段只要看见 `artifact_manifest_key` 有值就跳过，坏产物永远不会被重新生成，重试必然在同一处再次失败。
- 删除 `paper_imports.status` 改为从阶段推导：worker 领取要改成 JOIN 阶段表加 DISTINCT，失去单列索引。
- 删除 `paper_imports.error_code` 后由前端查失败阶段：列表页因此要展开全部阶段。
- 前后端各维护一份错误文案：两套文案必然漂移。
- 建立「错误码 → 用户文案」映射表：parse 阶段的文案来自 MinerU，其余错误各自手写，多一张表只是多一处要同步。
- 保留 `attempt` 或 `progress`：没有任何逻辑与界面读取；实时页数进度此次不做。

## RATIONALE

字段是否保留取决于有没有读取方，而不是「以后可能有用」。产物按 job 分层保护的是一个不存在的重跑场景，它造成的堆积却是确定的。错误文案属于产品的表达，应当与错误码一起由后端产生。

## OUT OF SCOPE

按解析器版本重解析；引用层面的产物版本回滚；MinerU 实时页数进度。

## OPEN

无。
