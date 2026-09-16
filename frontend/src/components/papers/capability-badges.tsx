import { Badge } from "@/components/ui/badge"
import type { Capabilities, ProcessingState } from "@/lib/api"

const CAPABILITY_LABELS: Array<[keyof Capabilities, string]> = [
  ["has_pdf", "PDF"],
  ["has_metadata", "元数据"],
  ["has_fulltext", "全文"],
  ["has_keyword_index", "关键词检索"],
  ["has_embedding", "语义检索"],
]

/** Each capability gates a different action, so show them separately. */
export function CapabilityBadges({ capabilities }: { capabilities: Capabilities }) {
  return (
    <div className="flex flex-wrap gap-1">
      {CAPABILITY_LABELS.map(([key, label]) => (
        <Badge key={key} variant={capabilities[key] ? "secondary" : "outline"}>
          {label}
        </Badge>
      ))}
    </div>
  )
}

const STAGE_LABELS: Record<string, string> = {
  metadata: "元数据",
  fulltext: "正文解析",
  chunking: "分块",
  embedding: "向量化",
}

/** 处理状态用统一语义色：完成=绿，失败=红，未完成=黄。 */
export function ProcessingBadge({ processing }: { processing: ProcessingState }) {
  if (!processing.status) {
    return <Badge variant="outline">未处理</Badge>
  }
  if (processing.status === "succeeded") {
    return <Badge variant="success">完成</Badge>
  }
  if (processing.status === "failed") {
    const stage = processing.current_stage
    return (
      <Badge variant="destructive">
        {stage ? `${STAGE_LABELS[stage] ?? stage}失败` : "失败"}
      </Badge>
    )
  }
  const label = processing.current_stage
    ? `${STAGE_LABELS[processing.current_stage] ?? processing.current_stage}中`
    : "排队中"
  return <Badge variant="warning">{label}</Badge>
}

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage
}
