import { FileText } from "lucide-react"

import { usePaperOpen } from "@/components/chat/CitationProvider"
import { getResultText } from "@/components/chat/toolRenderers/shared"
import type { ToolCallWithResult, ToolRenderer } from "@/components/chat/toolRenderers/types"
import type { ToolListedPaper } from "@/types/chat"

function readPapers(pair: ToolCallWithResult): ToolListedPaper[] | null {
  const text = getResultText(pair.result)
  try {
    const data: unknown = JSON.parse(text)
    // The internal list endpoint is compact on purpose: one entry per paper
    // with only what a list needs, keyed by the user's own entry id.
    if (!data || typeof data !== "object" || !("papers" in data)) return null
    if (!Array.isArray(data.papers)) return null
    return data.papers.filter((item): item is ToolListedPaper =>
      Boolean(
        item &&
        typeof item === "object" &&
        "paper_id" in item &&
        typeof item.paper_id === "string",
      ),
    )
  } catch {
    return null
  }
}

function PaperCard({
  paper,
  onOpen,
}: {
  paper: ToolListedPaper
  onOpen: (() => void) | null
}) {
  const title = paper.title || "未命名文献"
  const authors = paper.authors?.length ? paper.authors.join("、") : null
  const meta = [paper.venue, paper.year].filter(Boolean).join(" · ")
  const state = paper.has_fulltext ? "可检索" : "待补全文"
  const className =
    "block w-full rounded-lg border bg-background p-3 text-left text-sm transition-colors hover:bg-accent"
  const body = (
    <>
      <span className="flex items-start gap-2">
        <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <span className="line-clamp-2 font-medium break-words" title={title}>
          {title}
        </span>
      </span>
      {authors && (
        <span
          className="mt-1 line-clamp-1 block break-words text-muted-foreground"
          title={authors}
        >
          {authors}
        </span>
      )}
      <span className="mt-2 flex flex-wrap gap-x-2 text-xs text-muted-foreground">
        {meta && <span title={meta}>{meta}</span>}
        <span>{state}</span>
      </span>
    </>
  )
  // Without a sidebar there is nowhere to open the paper, so the card stays
  // a plain block instead of offering a dead click.
  if (!onOpen) return <div className={className}>{body}</div>
  return (
    <button type="button" className={className} onClick={onOpen}>
      {body}
    </button>
  )
}

function PaperList({ pair }: { pair: ToolCallWithResult }) {
  const openPaper = usePaperOpen()
  const papers = readPapers(pair)
  if (pair.result?.state === "error" || papers === null) {
    return <p role="alert" className="p-3 text-sm text-destructive">无法读取文献列表，请重试</p>
  }
  if (!papers.length) return <p className="p-3 text-sm text-muted-foreground">暂无文献</p>
  return (
    <div className="space-y-2 py-2">
      {papers.map((paper) => (
        <PaperCard
          key={paper.paper_id}
          paper={paper}
          onOpen={
            openPaper
              ? () =>
                  openPaper({
                    kind: "paper",
                    user_paper_id: paper.paper_id,
                    page: null,
                  })
              : null
          }
        />
      ))}
    </div>
  )
}

export const ListPapersRenderer: ToolRenderer = {
  renderHeader: () => <span>列出文献</span>,
  renderBody: (pair) => (pair.result ? <PaperList pair={pair} /> : null),
}
