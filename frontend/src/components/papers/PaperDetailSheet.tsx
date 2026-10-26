import { useMutation, useQuery } from "@tanstack/react-query"
import { MessageSquarePlus } from "lucide-react"
import { useNavigate } from "react-router-dom"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/Alert"
import { Badge } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/Sheet"
import { Skeleton } from "@/components/ui/Skeleton"
import { Spinner } from "@/components/ui/Spinner"
import { Textarea } from "@/components/ui/Textarea"
import { AddToProjectMenu } from "@/components/papers/AddToProjectMenu"
import { PaperStatusBadge } from "@/components/papers/PaperStatus"
import { useApi } from "@/components/providers/ApiProvider"
import { useAgentUi } from "@/components/providers/AgentUiProvider"
import { describeError, notifyError } from "@/lib/errors"
import { queryKeys } from "@/app/query"

export function PaperDetailSheet({
  paperId,
  onOpenChange,
}: {
  paperId: string | null
  onOpenChange: (open: boolean) => void
}) {
  const { api } = useApi()
  const agentUi = useAgentUi()
  const navigate = useNavigate()

  const detail = useQuery({
    queryKey: queryKeys.paper(paperId ?? "none"),
    queryFn: () => api.library.detail(paperId as string),
    enabled: Boolean(paperId),
    refetchInterval: (query) => {
      const status = query.state.data?.run_status
      return status === "pending" || status === "running" ? 1500 : false
    },
  })

  // 单篇文献会话只覆盖这一篇，不属于任何项目。
  const startSession = useMutation({
    mutationFn: () =>
      api.sessions.create({
        paper_id: paperId as string,
        title: detail.data?.title ?? undefined,
      }),
    onSuccess: (session) => {
      onOpenChange(false)
      navigate(`/sessions/${session.id}`)
    },
    onError: (error) => notifyError(error, "创建会话失败"),
  })

  const paper = detail.data

  return (
    <Sheet open={Boolean(paperId)} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="gap-0 overflow-hidden data-[side=right]:w-full data-[side=right]:sm:max-w-4xl">
        <SheetHeader className="border-border/60 border-b">
          <SheetTitle className="pr-8">{paper?.title ?? "文献详情"}</SheetTitle>
          <SheetDescription>
            {paper
              ? `${paper.authors.join("、") || "作者未知"}${paper.year ? ` · ${paper.year}` : ""}`
              : "加载中…"}
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto p-4">
          {detail.isPending ? (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-40 w-full" />
            </div>
          ) : detail.isError ? (
            <Alert variant="destructive">
              <AlertTitle>读取失败</AlertTitle>
              <AlertDescription>{describeError(detail.error)}</AlertDescription>
            </Alert>
          ) : paper ? (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-center gap-2">
                <PaperStatusBadge
                  capabilities={paper.capabilities}
                  runStatus={paper.run_status}
                />
                {paper.doi ? <Badge variant="outline">DOI {paper.doi}</Badge> : null}
                {paper.arxiv_id ? (
                  <Badge variant="outline">arXiv {paper.arxiv_id}</Badge>
                ) : null}
              </div>

              <section className="flex flex-col gap-2">
                <h3 className="text-sm font-medium">书目信息</h3>
                <dl className="grid grid-cols-[7rem_1fr] gap-y-1 text-sm">
                  <dt className="text-muted-foreground">书目信息</dt>
                  <dd>{paper.capabilities.has_metadata ? "已补全" : "待补全"}</dd>
                  <dt className="text-muted-foreground">期刊/会议</dt>
                  <dd>{paper.venue ?? "—"}</dd>
                  <dt className="text-muted-foreground">页数</dt>
                  <dd>{paper.pdf.page_count ?? "—"}</dd>
                </dl>
                {paper.abstract ? (
                  <Textarea
                    readOnly
                    value={paper.abstract}
                    className="max-h-40 min-h-24 resize-none text-sm"
                  />
                ) : null}
              </section>

            </div>
          ) : null}
        </div>

        <div className="border-border/60 flex items-center justify-end gap-2 border-t p-3">
          {paperId ? <AddToProjectMenu paperId={paperId} /> : null}
          {!agentUi && <Button
            size="sm"
            disabled={startSession.isPending}
            onClick={() => startSession.mutate()}
          >
            {startSession.isPending ? (
              <Spinner data-icon="inline-start" />
            ) : (
              <MessageSquarePlus data-icon="inline-start" />
            )}
            提问
          </Button>}
        </div>
      </SheetContent>
    </Sheet>
  )
}
