import { Check, Circle, LoaderCircle, Undo2, X } from "lucide-react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { useApi } from "@/components/providers/ApiProvider"
import { PaperDetailSheet } from "@/components/papers/PaperDetailSheet"
import { useImportQueue } from "@/components/providers/ImportQueueProvider"
import { Button } from "@/components/ui/Button"
import { Spinner } from "@/components/ui/Spinner"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/Sheet"
import { paperProcessingStatusLabel, paperStageLabel, paperStageRank } from "@/lib/papers/vocabulary"
import type { ImportQueueItem } from "@/types/business"

const ERROR_TEXT: Record<string, string> = {
  import_source_unavailable: "没有找到可用的源文件",
  paper_pdf_not_available: "没有找到可用的源文件",
  provider_not_configured: "对应服务未配置",
  provider_unavailable: "上游服务暂时不可用",
  provider_rate_limited: "上游服务限流",
  import_artifact_invalid: "解析产物不兼容或损坏",
  internal_error: "内部错误",
}

const STATUS_TONE: Record<string, string> = {
  ready: "text-success",
  failed: "text-destructive",
  source_unavailable: "text-warning",
}

const RETRYABLE = new Set(["failed", "source_unavailable"])

function QueueRow({
  item,
  openPaper,
  onRetry,
  retrying,
}: {
  item: ImportQueueItem
  openPaper: (paperId: string) => void
  onRetry: (importId: string) => void
  retrying: boolean
}) {
  const active = item.status === "queued" || item.status === "running"
  const title = item.title || item.identifier || "文献入库"

  return (
    <div className="flex flex-col gap-2 rounded-lg px-3 py-2 hover:bg-muted/40">
      <div className="flex items-center gap-2">
        {item.paper_id ? (
          <button
            type="button"
            onClick={() => openPaper(item.paper_id!)}
            className="min-w-0 flex-1 truncate text-left font-medium"
          >
            {title}
          </button>
        ) : (
          <span className="min-w-0 flex-1 truncate font-medium">{title}</span>
        )}
        {active && <LoaderCircle aria-label="进行中" className="size-4 shrink-0 animate-spin" />}
        <span className={`shrink-0 text-xs ${STATUS_TONE[item.status] ?? "text-muted-foreground"}`}>
          {importStatusLabel(item)}
        </span>
        {RETRYABLE.has(item.status) && (
          <Button size="sm" variant="ghost" disabled={retrying} onClick={() => onRetry(item.id)}>
            {retrying ? <Spinner data-icon="inline-start" /> : <Undo2 data-icon="inline-start" />}
            重试
          </Button>
        )}
      </div>

      <ol className="flex flex-wrap gap-x-4 gap-y-1 pl-1" aria-label="入库进度">
        {[...item.stages]
          .sort((a, b) => paperStageRank(a.stage) - paperStageRank(b.stage))
          .map((stage) => {
            const failed = stage.status === "failed"
            const running = stage.status === "running"
            const done = stage.status === "succeeded"
            const Icon = failed ? X : running ? LoaderCircle : done ? Check : Circle
            return (
              <li
                key={stage.stage}
                className={`flex items-center gap-1 text-xs ${
                  failed ? "text-destructive" : running ? "text-primary" : done ? "text-success" : "text-muted-foreground"
                }`}
              >
                <Icon aria-hidden="true" className={`size-3 ${running ? "animate-spin" : ""}`} />
                {paperStageLabel(stage.stage)}
              </li>
            )
          })}
      </ol>

      {item.error_code && RETRYABLE.has(item.status) && (
        <p className="text-muted-foreground text-xs">{ERROR_TEXT[item.error_code] ?? "入库未完成"}</p>
      )}
    </div>
  )
}

function importStatusLabel(item: ImportQueueItem): string {
  if (item.status === "ready") return "已完成"
  if (item.status === "source_unavailable") return "缺少原文"
  if (item.status === "failed") return "失败"
  const stage = item.stages.find((entry) => entry.status === "running")
  return stage ? paperProcessingStatusLabel("running") : paperProcessingStatusLabel("pending")
}

export function ImportQueuePanel() {
  const { open, setOpen, items, loading, error } = useImportQueue()
  const { api } = useApi()
  const queryClient = useQueryClient()
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null)

  function openPaper(paperId: string) {
    setOpen(false)
    setSelectedPaperId(paperId)
  }

  const retry = useMutation({
    mutationFn: (importId: string) => api.imports.retry(importId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["import-queue"] })
      void queryClient.invalidateQueries({ queryKey: ["papers"] })
    },
  })

  return (
    <>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="w-110! max-w-[90vw]! gap-0 p-0">
          <SheetHeader className="border-b px-5 py-4">
            <SheetTitle>入库队列</SheetTitle>
            <SheetDescription>完成入库的文献才会出现在文献库</SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            {loading && <p className="text-muted-foreground p-3 text-sm">加载中…</p>}
            {error && <p role="alert" className="text-destructive p-3 text-sm">队列加载失败</p>}
            {!loading && !error && items.length === 0 && (
              <p className="text-muted-foreground p-3 text-sm">暂无入库任务</p>
            )}
            {items.map((item) => (
              <QueueRow
                key={item.id}
                item={item}
                openPaper={openPaper}
                retrying={retry.isPending && retry.variables === item.id}
                onRetry={(importId) => retry.mutate(importId)}
              />
            ))}
          </div>
        </SheetContent>
      </Sheet>
      <PaperDetailSheet
        paperId={selectedPaperId}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) setSelectedPaperId(null)
        }}
      />
    </>
  )
}
