import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  FileUp,
  MessageSquarePlus,
  RefreshCw,
  Sparkles,
  TriangleAlert,
  Undo2,
} from "lucide-react"
import { useRef, useState } from "react"
import { useNavigate } from "react-router-dom"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { AddToProjectMenu } from "@/components/papers/add-to-project-menu"
import { CapabilityBadges, ProcessingBadge, stageLabel } from "@/components/papers/capability-badges"
import { PdfViewer } from "@/components/papers/pdf-viewer"
import { useApi } from "@/lib/api/provider"
import { describeError, notifyError, notifySuccess } from "@/lib/errors"
import { queryKeys } from "@/app/query"

const STAGE_ERROR_TEXT: Record<string, string> = {
  provider_not_configured: "对应服务未配置，无法执行该阶段",
  provider_unavailable: "上游服务暂时不可用",
  provider_rate_limited: "上游服务限流",
  metadata_provider_failed: "元数据服务失败，正文处理不受影响",
  metadata_not_found: "没有查询到该标识符",
  ingestion_artifact_invalid: "解析产物不兼容或损坏",
  paper_pdf_not_available: "没有可用的 PDF",
}

const STATUS_LABEL: Record<string, string> = {
  pending: "待执行",
  running: "进行中",
  succeeded: "完成",
  failed: "失败",
  skipped: "已跳过",
}

export function PaperDetailSheet({
  paperId,
  onOpenChange,
}: {
  paperId: string | null
  onOpenChange: (open: boolean) => void
}) {
  const { api } = useApi()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const fileInput = useRef<HTMLInputElement>(null)

  const detail = useQuery({
    queryKey: queryKeys.paper(paperId ?? "none"),
    queryFn: () => api.library.detail(paperId as string),
    enabled: Boolean(paperId),
    refetchInterval: (query) => {
      const status = query.state.data?.processing.status
      return status === "queued" || status === "running" ? 1500 : false
    },
  })

  const job = useQuery({
    queryKey: queryKeys.ingestionJob(detail.data?.processing.job_id ?? "none"),
    queryFn: () => api.library.ingestionJob(detail.data!.processing.job_id as string),
    enabled: Boolean(detail.data?.processing.job_id),
    refetchInterval: (query) =>
      query.state.data?.status === "queued" || query.state.data?.status === "running"
        ? 1500
        : false,
  })

  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ title: "", doi: "", arxiv_id: "" })

  function refreshAll() {
    void queryClient.invalidateQueries({ queryKey: ["papers"] })
    void queryClient.invalidateQueries({ queryKey: queryKeys.paper(paperId ?? "none") })
    void queryClient.invalidateQueries({ queryKey: ["ingestion-job"] })
  }

  const attachPdf = useMutation({
    mutationFn: (file: File) => api.library.attachPdf(paperId as string, file),
    onSuccess: () => {
      notifySuccess("PDF 已补入该条目")
      refreshAll()
    },
    onError: (error) => notifyError(error, "补传 PDF 失败"),
  })

  const fetchPdf = useMutation({
    mutationFn: () => api.library.fetchPdf(paperId as string),
    onSuccess: (result) => {
      if (result.metadata.status === "provider_failed") {
        notifyError(new Error(describeError(result.metadata.error_code)), "获取全文失败")
      } else {
        notifySuccess("已尝试获取全文")
      }
      refreshAll()
    },
    onError: (error) => notifyError(error, "获取全文失败"),
  })

  const resolveMetadata = useMutation({
    mutationFn: () => api.library.resolveMetadata(paperId as string),
    onSuccess: (result) => {
      const applied = result.metadata.applied_fields
      notifySuccess(
        applied.length > 0 ? `已补全：${applied.join("、")}` : "元数据没有新的可补全字段",
      )
      refreshAll()
    },
    onError: (error) => notifyError(error, "补全元数据失败"),
  })

  const patchMetadata = useMutation({
    mutationFn: () =>
      api.library.patchMetadata(paperId as string, {
        title: form.title || undefined,
        doi: form.doi || undefined,
        arxiv_id: form.arxiv_id || undefined,
      }),
    onSuccess: () => {
      notifySuccess("已保存")
      setEditing(false)
      refreshAll()
    },
    onError: (error) => notifyError(error, "保存失败"),
  })

  const retry = useMutation({
    mutationFn: (jobId: string) => api.library.retryIngestionJob(jobId),
    onSuccess: () => {
      notifySuccess("已重新排队处理")
      refreshAll()
    },
    onError: (error) => notifyError(error, "重试失败"),
  })

  const startSession = useMutation({
    mutationFn: () => api.sessions.create({ title: detail.data?.title ?? undefined }),
    onSuccess: (session) => {
      onOpenChange(false)
      navigate(`/sessions/${session.id}`)
    },
    onError: (error) => notifyError(error, "创建会话失败"),
  })

  const paper = detail.data

  return (
    <Sheet open={Boolean(paperId)} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 overflow-hidden sm:max-w-4xl">
        <SheetHeader className="border-border/60 border-b">
          <SheetTitle className="pr-8">{paper?.title ?? "论文详情"}</SheetTitle>
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
                <ProcessingBadge processing={paper.processing} />
                <Badge variant="outline">{paper.source}</Badge>
                {paper.doi ? <Badge variant="outline">DOI {paper.doi}</Badge> : null}
                {paper.arxiv_id ? (
                  <Badge variant="outline">arXiv {paper.arxiv_id}</Badge>
                ) : null}
              </div>

              <CapabilityBadges capabilities={paper.capabilities} />

              {paper.processing.status === "failed" && paper.processing.job_id ? (
                <Alert variant="warning">
                  <TriangleAlert />
                  <AlertTitle>处理未完成</AlertTitle>
                  <AlertDescription className="flex flex-col gap-2">
                    <span>
                      {STAGE_ERROR_TEXT[paper.processing.error_code ?? ""] ??
                        paper.processing.error_code ??
                        "处理失败"}
                      。已完成的阶段能力仍然可用。
                    </span>
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-fit"
                      disabled={retry.isPending}
                      onClick={() => retry.mutate(paper.processing.job_id as string)}
                    >
                      {retry.isPending ? (
                        <Spinner data-icon="inline-start" />
                      ) : (
                        <Undo2 data-icon="inline-start" />
                      )}
                      重试处理
                    </Button>
                  </AlertDescription>
                </Alert>
              ) : null}

              {!paper.capabilities.has_pdf ? (
                <Alert>
                  <AlertTitle>待补全文</AlertTitle>
                  <AlertDescription className="flex flex-col gap-2">
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={fetchPdf.isPending}
                        onClick={() => fetchPdf.mutate()}
                      >
                        {fetchPdf.isPending ? (
                          <Spinner data-icon="inline-start" />
                        ) : (
                          <RefreshCw data-icon="inline-start" />
                        )}
                        重新获取全文
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => fileInput.current?.click()}
                      >
                        <FileUp data-icon="inline-start" />
                        上传 PDF
                      </Button>
                    </div>
                  </AlertDescription>
                </Alert>
              ) : null}

              {job.data ? (
                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>阶段</TableHead>
                        <TableHead>状态</TableHead>
                        <TableHead>说明</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {job.data.stages.map((stage) => (
                        <TableRow key={stage.stage}>
                          <TableCell>{stageLabel(stage.stage)}</TableCell>
                          <TableCell>
                            <Badge
                              variant={
                                stage.status === "failed"
                                  ? "destructive"
                                  : stage.status === "succeeded"
                                    ? "success"
                                    : stage.status === "skipped"
                                      ? "outline"
                                      : "warning"
                              }
                            >
                              {STATUS_LABEL[stage.status] ?? stage.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-muted-foreground text-xs">
                            {stage.error_message ??
                              (stage.progress
                                ? Object.entries(stage.progress)
                                    .map(([key, value]) => `${key}=${String(value)}`)
                                    .join(" ")
                                : "—")}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : null}

              <Separator />

              <section className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium">书目信息</h3>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={resolveMetadata.isPending}
                      onClick={() => resolveMetadata.mutate()}
                    >
                      {resolveMetadata.isPending ? (
                        <Spinner data-icon="inline-start" />
                      ) : (
                        <Sparkles data-icon="inline-start" />
                      )}
                      补全元数据
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setForm({
                          title: paper.title ?? "",
                          doi: paper.doi ?? "",
                          arxiv_id: paper.arxiv_id ?? "",
                        })
                        setEditing((value) => !value)
                      }}
                    >
                      修正标识符
                    </Button>
                  </div>
                </div>
                {editing ? (
                  <form
                    className="flex flex-col gap-3 rounded-md border p-3"
                    onSubmit={(event) => {
                      event.preventDefault()
                      patchMetadata.mutate()
                    }}
                  >
                    <div className="flex flex-col gap-2">
                      <Label htmlFor="title">标题</Label>
                      <Input
                        id="title"
                        value={form.title}
                        onChange={(event) =>
                          setForm((prev) => ({ ...prev, title: event.target.value }))
                        }
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="flex flex-col gap-2">
                        <Label htmlFor="doi">DOI</Label>
                        <Input
                          id="doi"
                          value={form.doi}
                          onChange={(event) =>
                            setForm((prev) => ({ ...prev, doi: event.target.value }))
                          }
                        />
                      </div>
                      <div className="flex flex-col gap-2">
                        <Label htmlFor="arxiv">arXiv</Label>
                        <Input
                          id="arxiv"
                          value={form.arxiv_id}
                          onChange={(event) =>
                            setForm((prev) => ({ ...prev, arxiv_id: event.target.value }))
                          }
                        />
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button type="submit" size="sm" disabled={patchMetadata.isPending}>
                        保存修正
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => setEditing(false)}
                      >
                        取消
                      </Button>
                    </div>
                  </form>
                ) : null}
                <dl className="grid grid-cols-[7rem_1fr] gap-y-1 text-sm">
                  <dt className="text-muted-foreground">元数据状态</dt>
                  <dd>{paper.metadata_status}</dd>
                  <dt className="text-muted-foreground">文件名</dt>
                  <dd className="truncate">{paper.original_filename ?? "—"}</dd>
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

              {paper.capabilities.has_pdf ? (
                <section className="flex flex-col gap-2">
                  <h3 className="text-sm font-medium">原文</h3>
                  <div className="h-[28rem] overflow-hidden rounded-md border">
                    <PdfViewer paperId={paper.id} />
                  </div>
                </section>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="border-border/60 flex items-center justify-end gap-2 border-t p-3">
          <input
            ref={fileInput}
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) {
                attachPdf.mutate(file)
              }
              event.target.value = ""
            }}
          />
          {paperId ? <AddToProjectMenu paperId={paperId} /> : null}
          <Button
            size="sm"
            disabled={startSession.isPending}
            onClick={() => startSession.mutate()}
          >
            <MessageSquarePlus data-icon="inline-start" />
            就用这篇提问
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
