import { Badge } from "@upstream/components/ui/badge"
import type { Capabilities, ProcessingState } from "@/lib/api"

type Status = "done" | "failed" | "pending" | "idle"

/**
 * 一个条目只有一种对用户有意义的状态：
 * 可检索（绿）/ 处理失败（红）/ 处理中或待补全文（黄）/ 未处理（中性）。
 * 具体缺什么由详情面板按需说明，不在列表里堆术语。
 */
export function paperStatus(
  capabilities: Pick<Capabilities, "has_pdf" | "has_fulltext">,
  processing: ProcessingState,
): Status {
  if (processing.status === "failed") {
    return "failed"
  }
  if (processing.status === "queued" || processing.status === "running") {
    return "pending"
  }
  if (!capabilities.has_pdf) {
    return "idle"
  }
  if (capabilities.has_fulltext) {
    return "done"
  }
  return "pending"
}

const LABEL: Record<Status, string> = {
  done: "可检索",
  failed: "处理失败",
  pending: "处理中",
  idle: "待补全文",
}

const STYLE: Record<Status, string> = {
  done: "border-success/30 bg-success/10 text-success",
  failed: "border-destructive/30 bg-destructive/10 text-destructive",
  pending: "border-warning/30 bg-warning/10 text-warning",
  idle: "",
}

export function PaperStatusBadge({
  capabilities,
  processing,
}: {
  capabilities: Pick<Capabilities, "has_pdf" | "has_fulltext">
  processing: ProcessingState
}) {
  const status = paperStatus(capabilities, processing)
  return <Badge variant="outline" className={STYLE[status]}>{LABEL[status]}</Badge>
}

const STAGE_LABELS: Record<string, string> = {
  metadata: "元数据",
  fulltext: "正文解析",
  chunking: "分块",
  embedding: "向量化",
}

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage
}
