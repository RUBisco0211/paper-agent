/**
 * Shared user-facing vocabulary for paper import and retrieval.
 *
 * The backend owns the stage and status values; this module is the single
 * place that turns them into text, so adding a stage or error state does not
 * require touching every panel that displays it.
 */

export const PAPER_STAGE_ORDER = ["source", "parse", "chunk", "embed"] as const

const PAPER_STAGE_LABEL: Record<string, string> = {
  source: "获取原文",
  parse: "解析正文",
  chunk: "切分片段",
  embed: "生成向量",
}

const PAPER_PROCESSING_STATUS_LABEL: Record<string, string> = {
  pending: "待执行",
  running: "进行中",
  succeeded: "完成",
  matched: "已完成",
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
