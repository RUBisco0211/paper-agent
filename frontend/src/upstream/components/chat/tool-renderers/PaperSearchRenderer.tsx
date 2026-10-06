import { useCitationOpen } from "@upstream/components/chat/citation-context"
import { getResultText } from "./_shared"
import type { ToolCallWithResult, ToolRenderer } from "./types"

interface Evidence {
  citation_id: string
  snippet: string
  page_start: number | null
  page_end: number | null
}

function readSearch(pair: ToolCallWithResult): { status: string; evidence: Evidence[] } {
  const text = getResultText(pair.result)
  try {
    const data: unknown = JSON.parse(text)
    if (!data || typeof data !== "object" || !("evidence" in data) || !Array.isArray(data.evidence)) {
      return { status: "unavailable", evidence: [] }
    }
    return {
      status: "status" in data && typeof data.status === "string" ? data.status : "ok",
      evidence: data.evidence.filter((item): item is Evidence =>
        Boolean(item && typeof item.citation_id === "string" && typeof item.snippet === "string"),
      ),
    }
  } catch {
    return { status: "unavailable", evidence: [] }
  }
}

function PaperEvidence({ pair }: { pair: ToolCallWithResult }) {
  const openCitation = useCitationOpen()
  const { status, evidence } = readSearch(pair)
  if (pair.result?.state === "error" || status === "unavailable") {
    return <p role="alert" className="p-3 text-sm text-destructive">检索暂不可用，请重试</p>
  }
  if (!evidence.length) return <p className="p-3 text-sm text-muted-foreground">{status === "degraded" ? "检索已降级，未找到可引用的文献片段" : "没有可引用的文献片段"}</p>
  return (
    <div className="space-y-2 py-2">
      {status === "degraded" && <p className="text-xs text-muted-foreground">检索已降级，本次仅使用可用通道</p>}
      {evidence.map((item) => (
        <div key={item.citation_id} className="rounded-xl border bg-card p-3 text-sm">
          <p className="line-clamp-4 whitespace-pre-wrap">{item.snippet}</p>
          <button type="button" className="mt-2 text-xs font-medium underline" onClick={() => openCitation?.(item.citation_id)}>
            引用原文{item.page_start ? ` · 第 ${item.page_start}${item.page_end && item.page_end !== item.page_start ? `–${item.page_end}` : ""} 页` : ""}
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
