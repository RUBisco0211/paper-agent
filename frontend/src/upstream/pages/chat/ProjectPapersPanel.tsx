import { useQuery } from "@tanstack/react-query"
import { FileText } from "lucide-react"
import { useContext, useEffect, useState } from "react"

import { useApi } from "@/lib/api/provider"
import { PaperReadingPage } from "@/pages/paper-reading"
import type { PaperQuote, QuoteReference } from "@upstream/components/chat/quote-references"
import { ChatQuoteContext } from "./ChatQuoteContext"

export function ProjectPapersPanel({ projectId, sessionId, onReadingChange }: { projectId: string; sessionId: string | null; onReadingChange?: (reading: boolean) => void }) {
  const { api } = useApi()
  const [readingId, setReadingId] = useState<string | null>(null)
  const [locatedQuote, setLocatedQuote] = useState<PaperQuote | null>(null)
  useEffect(() => onReadingChange?.(Boolean(readingId)), [readingId, onReadingChange])
  const quoteBridge = useContext(ChatQuoteContext)
  useEffect(() => {
    if (!sessionId) return
    return quoteBridge?.registerPaperOpener(sessionId, (reference) => {
      setReadingId(reference.user_paper_id)
      setLocatedQuote(reference)
      return true
    })
  }, [quoteBridge, sessionId])
  const papers = useQuery({ queryKey: ["project-papers", projectId], queryFn: () => api.projects.papers(projectId, { limit: 200 }) })
  const items = papers.data?.items ?? []

  function addQuote(reference: QuoteReference) {
    return Boolean(sessionId && quoteBridge?.add(sessionId, reference))
  }

  if (readingId) return <PaperReadingPage paperId={readingId} embedded locatedQuote={locatedQuote} onBack={() => { setReadingId(null); setLocatedQuote(null) }} onQuote={sessionId ? addQuote : undefined} />

  return <aside aria-label="项目文献" className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
      <div className="flex-1 overflow-y-auto p-2">
        {papers.isPending && <p className="p-2 text-sm text-muted-foreground">加载中…</p>}
        {papers.isError && <p role="alert" className="p-2 text-sm text-destructive">无法读取项目文献</p>}
        {papers.isSuccess && items.length === 0 && <p className="p-2 text-sm text-muted-foreground">暂无文献</p>}
        {items.map((item) => <button key={item.id} type="button" onClick={() => { setReadingId(item.id); setLocatedQuote(null) }} className="flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-muted"><FileText className="mt-0.5 size-4 shrink-0" /><span className="line-clamp-2">{item.title || item.original_filename || "未命名文献"}</span></button>)}
      </div>
    </aside>
}
