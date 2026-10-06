import { useQuery } from "@tanstack/react-query"

import { PdfViewer } from "@/components/papers/pdf-viewer"
import { useApi } from "@/lib/api/provider"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@upstream/components/ui/sheet"

interface BoundCitation {
  citation_id: string
  paper_id: string
  title_path: string | null
  snippet: string
  page_start: number | null
  page_end: number | null
}

export function BoundCitationSheet({
  sessionId,
  citationId,
  onOpenChange,
}: {
  sessionId: string
  citationId: string | null
  onOpenChange: (open: boolean) => void
}) {
  const { api } = useApi()
  const citation = useQuery({
    queryKey: ["bound-citation", sessionId, citationId],
    queryFn: () => api.client.request<BoundCitation>(
      `/v1/session-bindings/${sessionId}/citations/${citationId}`,
    ),
    enabled: Boolean(citationId),
  })
  const paper = useQuery({
    queryKey: ["paper", citation.data?.paper_id],
    queryFn: () => api.library.detail(citation.data!.paper_id),
    enabled: Boolean(citation.data?.paper_id),
  })

  return (
    <Sheet open={Boolean(citationId)} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-3xl">
        <SheetHeader>
          <SheetTitle>引用原文</SheetTitle>
          <SheetDescription>{paper.data?.title ?? "文献"}{citation.data?.page_start ? ` · 第 ${citation.data.page_start}${citation.data.page_end && citation.data.page_end !== citation.data.page_start ? `–${citation.data.page_end}` : ""} 页` : ""}</SheetDescription>
        </SheetHeader>
        {citation.isPending && <p className="p-4 text-sm">加载中…</p>}
        {citation.isError && <p role="alert" className="p-4 text-sm text-destructive">无法打开引用原文</p>}
        {citation.data && <div className="space-y-4 p-4">
          <blockquote className="rounded-xl border bg-muted p-3 text-sm whitespace-pre-wrap">{citation.data.snippet}</blockquote>
          {citation.data.title_path && <p className="text-sm text-muted-foreground">{citation.data.title_path}</p>}
          {paper.data?.pdf.available && <div className="h-[28rem] overflow-hidden rounded-xl border">
            <PdfViewer paperId={citation.data.paper_id} page={citation.data.page_start} />
          </div>}
        </div>}
      </SheetContent>
    </Sheet>
  )
}
