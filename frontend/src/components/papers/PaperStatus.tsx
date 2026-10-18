import { Badge } from "@/components/ui/Badge"
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

const VARIANT = {
  done: "success",
  failed: "destructive",
  pending: "warning",
  idle: "outline",
} as const

export function PaperStatusBadge({
  capabilities,
  processing,
}: {
  capabilities: Pick<Capabilities, "has_pdf" | "has_fulltext">
  processing: ProcessingState
}) {
  const status = paperStatus(capabilities, processing)
  return <Badge variant={VARIANT[status]}>{LABEL[status]}</Badge>
}
