import { useQuery } from "@tanstack/react-query"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Separator } from "@/components/ui/separator"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { PdfViewer } from "@/components/papers/pdf-viewer"
import { useApi } from "@/lib/api/provider"
import { describeError } from "@/lib/errors"
import { queryKeys } from "@/app/query"

/**
 * Show the evidence behind one citation.
 *
 * Only ids the backend stored for this session can be resolved; the model
 * cannot invent a citation and the UI cannot fetch another session's evidence.
 */
export function CitationSheet({
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
    queryKey: queryKeys.search({ citationId, sessionId }),
    queryFn: () => api.sessions.citation(sessionId, citationId as string),
    enabled: Boolean(citationId),
  })

  return (
    <Sheet open={Boolean(citationId)} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 overflow-hidden sm:max-w-3xl">
        <SheetHeader className="border-border/60 border-b">
          <SheetTitle>引用原文</SheetTitle>
          <SheetDescription>
            {citation.data?.title_path ?? "论文片段"}
            {citation.data?.page_start
              ? ` · 第 ${citation.data.page_start}${
                  citation.data.page_end && citation.data.page_end !== citation.data.page_start
                    ? `–${citation.data.page_end}`
                    : ""
                } 页`
              : " · 无可靠页码"}
          </SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto p-4">
          {citation.isPending ? (
            <Skeleton className="h-32 w-full" />
          ) : citation.isError ? (
            <Alert variant="destructive">
              <AlertTitle>无法展开引用</AlertTitle>
              <AlertDescription>{describeError(citation.error)}</AlertDescription>
            </Alert>
          ) : citation.data ? (
            <div className="flex flex-col gap-4">
              <blockquote className="bg-muted/50 rounded-md border-l-2 p-3 text-sm whitespace-pre-wrap">
                {citation.data.snippet}
              </blockquote>
              <Separator />
              <div className="h-[26rem] overflow-hidden rounded-md border">
                <PdfViewer paperId={citation.data.paper_id} page={citation.data.page_start} />
              </div>
            </div>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  )
}
