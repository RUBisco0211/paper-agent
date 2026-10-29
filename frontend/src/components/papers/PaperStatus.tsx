import { Badge } from "@/components/ui/Badge"
import type { Capabilities, RunStatus } from "@/lib/api"

type Status = "done" | "failed" | "pending" | "idle"

/**
 * 一个条目只有一种对用户有意义的状态：
 * 可检索（绿）/ 处理失败（红）/ 处理中或待补全文（黄）/ 未处理（中性）。
 * 具体缺什么由详情面板按需说明，不在列表里堆术语。
 */
export function paperStatus(
  capabilities: Pick<Capabilities, "has_source" | "has_parsed">,
  runStatus?: RunStatus | null,
): Status {
  if (runStatus === "failed") {
    return "failed"
  }
  if (runStatus === "pending" || runStatus === "running") {
    return "pending"
  }
  if (!capabilities.has_source) {
    return "idle"
  }
  if (capabilities.has_parsed) {
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
  runStatus,
}: {
  capabilities: Pick<Capabilities, "has_source" | "has_parsed">
  runStatus?: RunStatus | null
}) {
  const status = paperStatus(capabilities, runStatus)
  return <Badge variant={VARIANT[status]}>{LABEL[status]}</Badge>
}
