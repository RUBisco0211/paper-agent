import { useCitationOpen } from "@/components/chat/CitationProvider"
import { getResultText } from "@/components/chat/toolRenderers/shared"
import type { ToolSearchEvidence } from "@/types/chat"
import type { ToolCallWithResult, ToolRenderer } from "./types"

/** Shown whenever only some retrieval channels contributed. */
const DEGRADED_HINT = "请检查查询向量化服务是否可用"

function readSearch(pair: ToolCallWithResult): { status: string; evidence: ToolSearchEvidence[] } {
  const text = getResultText(pair.result)
  try {
    const data: unknown = JSON.parse(text)
    if (!data || typeof data !== "object" || !("evidence" in data) || !Array.isArray(data.evidence)) {
      return { status: "unavailable", evidence: [] }
    }
    return {
      status: "status" in data && typeof data.status === "string" ? data.status : "ok",
      evidence: data.evidence.filter((item): item is ToolSearchEvidence =>
        Boolean(item && typeof item.citation_id === "string" && typeof item.snippet === "string"),
      ),
    }
  } catch {
    return { status: "unavailable", evidence: [] }
  }
}

/**
 * A degraded search still returns usable evidence, so the hint sits above the
 * list rather than replacing it.
 */
function DegradedHint({ status }: { status: string }) {
  if (status !== "degraded") return null
  return <p className="text-xs text-muted-foreground">{DEGRADED_HINT}</p>
}

function PaperEvidence({ pair }: { pair: ToolCallWithResult }) {
  const openCitation = useCitationOpen()
  const { status, evidence } = readSearch(pair)
  if (pair.result?.state === "error" || status === "unavailable") {
    return <p role="alert" className="p-3 text-sm text-destructive">检索暂不可用，请重试</p>
  }
  if (!evidence.length) {
    return (
      <div className="space-y-1 p-3 text-sm text-muted-foreground">
        <p>{status === "degraded" ? "检索已降级，未找到可引用的文献片段" : "没有可引用的文献片段"}</p>
        <DegradedHint status={status} />
      </div>
    )
  }
  return (
    <div className="space-y-2 py-2">
      <DegradedHint status={status} />
      {evidence.map((item) => (
        <div key={item.citation_id} className="rounded-lg border bg-card p-3 text-sm">
          <p className="line-clamp-4 whitespace-pre-wrap">{item.snippet}</p>
          <button type="button" className="mt-2 text-xs font-medium underline" onClick={() => openCitation?.(item.citation_id)}>
            查看详情{item.page_start ? ` · 第 ${item.page_start}${item.page_end && item.page_end !== item.page_start ? `–${item.page_end}` : ""} 页` : ""}
          </button>
        </div>
      ))}
    </div>
  )
}

export const PaperSearchRenderer: ToolRenderer = {
  renderHeader: () => <span>检索文献</span>,
  renderBody: (pair) => pair.result ? <PaperEvidence pair={pair} /> : null,
}
