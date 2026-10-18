/**
 * Shared user-facing vocabulary for paper ingestion and retrieval.
 *
 * The backend owns the stage and status values; this module is the single
 * place that turns them into text, so adding a stage or error state does not
 * require touching every panel that displays it.
 */

export const PAPER_STAGE_ORDER = [
  "metadata",
  "fulltext",
  "chunking",
  "embedding",
] as const

const PAPER_STAGE_LABEL: Record<string, string> = {
  metadata: "元数据",
  fulltext: "正文解析",
  chunking: "分块",
  embedding: "向量化",
}

const PAPER_PROCESSING_STATUS_LABEL: Record<string, string> = {
  pending: "待执行",
  running: "进行中",
  succeeded: "完成",
  matched: "已完成",
  failed: "失败",
  skipped: "已跳过",
}

const IMPORT_QUEUE_LABEL: Record<string, string> = {
  queued: "排队中",
  resolving: "获取元数据",
  metadata_ready: "元数据已就绪",
  downloading: "获取全文",
  pdf_unavailable: "等待全文",
  ready: "已完成",
  running: "处理中",
  succeeded: "已完成",
  failed: "失败",
}

export function paperStageLabel(stage: string): string {
  return PAPER_STAGE_LABEL[stage] ?? stage
}

/** Sort rank for a stage, matching the order shown in the detail panel. */
export function paperStageRank(stage: string): number {
  return PAPER_STAGE_ORDER.indexOf(
    stage as (typeof PAPER_STAGE_ORDER)[number],
  )
}

export function paperProcessingStatusLabel(status: string): string {
  return PAPER_PROCESSING_STATUS_LABEL[status] ?? status
}

/** Label for an import-queue row, which exposes a stage or a queue status. */
export function importQueueLabel(value: string): string {
  return (
    PAPER_STAGE_LABEL[value] ??
    IMPORT_QUEUE_LABEL[value] ??
    PAPER_PROCESSING_STATUS_LABEL[value] ??
    "处理中"
  )
}
