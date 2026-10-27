import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Clock,
  LoaderCircle,
  RotateCw,
} from "lucide-react"
import { useState } from "react"

import { useApi } from "@/components/providers/ApiProvider"
import { notifyError, notifySuccess } from "@/lib/errors"
import { PaperDetailSheet } from "@/components/papers/PaperDetailSheet"
import { useImportQueue } from "@/components/providers/ImportQueueProvider"
import { Button } from "@/components/ui/Button"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/Sheet"
import type { DownloadStatus, ImportQueueItem, RunStage } from "@/types/business"

const STATUS_LABEL: Record<DownloadStatus, string> = {
  pending: "等待中",
  running: "处理中",
  success: "已完成",
  failed: "失败",
}

const STAGES: Array<{ stage: RunStage; label: string }> = [
  { stage: "parse", label: "解析正文" },
  { stage: "chunk", label: "切分片段" },
  { stage: "embed", label: "生成向量" },
]

type StepState = "done" | "failed" | "running" | "pending" | "skipped"

interface Step {
  key: string
  label: string
  state: StepState
}

/**
 * Every step the request actually had, as separate rows: a fetch (or the
 * upload), then the three processing stages in order. Collapsing them into a
 * single current stage hides how far along the paper really is.
 */
function stepsOf(item: ImportQueueItem): Step[] {
  const steps: Step[] = []
  if (item.source === "download") {
    steps.push({
      key: "fetch",
      label: "获取原文",
      state:
        item.status === "success"
          ? "done"
          : item.status === "failed"
            ? "failed"
            : item.status === "running"
              ? "running"
              : "pending",
    })
  } else {
    steps.push({ key: "upload", label: "文件上传", state: "done" })
  }

  const run = item.run
  if (run === null || run === undefined) {
    // Nothing was processed yet: the stages did not start.
    return steps
  }
  const finishedAt = run.stage_finished_at ?? {}
  const currentIndex = STAGES.findIndex((entry) => entry.stage === run.stage)
  STAGES.forEach((entry, index) => {
    const reached =
      run.status === "success" ||
      (currentIndex >= 0 && index <= currentIndex)
    steps.push({
      key: entry.stage,
      label: entry.label,
      state: !reached
        ? "pending"
        : finishedAt[entry.stage]
          ? "done"
          : run.status === "failed"
            ? "failed"
            : "running",
    })
  })
  return steps
}

/**
 * One glance at the row: done, running, failed, or still queued. The tone is
 * the only place colour carries meaning, so it is never doubled by text.
 */
function StatusIcon({ item }: { item: ImportQueueItem }) {
  if (hasFailed(item)) {
    return (
      <CircleAlert
        role="img"
        aria-label="失败"
        className="size-4 shrink-0 text-destructive"
      />
    )
  }
  if (item.status === "success" && item.run === null) {
    // The file is in; processing never started.
    return (
      <Clock role="img" aria-label="未开始处理" className="size-4 shrink-0 text-warning" />
    )
  }
  if (item.status === "success" && item.run?.status === "success") {
    return (
      <CircleCheck role="img" aria-label="已完成" className="size-4 shrink-0 text-success" />
    )
  }
  if (item.status === "pending" || item.status === "running") {
    return (
      <LoaderCircle
        role="img"
        aria-label="进行中"
        className="size-4 shrink-0 animate-spin text-primary"
      />
    )
  }
  // Waiting its turn: not started, not failed.
  return (
    <Clock role="img" aria-label="等待中" className="size-4 shrink-0 text-muted-foreground" />
  )
}

const STEP_TONE: Record<StepState, { dot: string; text: string }> = {
  done: { dot: "bg-success", text: "text-muted-foreground" },
  failed: { dot: "bg-destructive", text: "text-destructive" },
  running: { dot: "bg-primary", text: "text-primary" },
  pending: { dot: "bg-muted-foreground/40", text: "text-muted-foreground" },
  skipped: { dot: "bg-muted-foreground/40", text: "text-muted-foreground" },
}

const STEP_TEXT: Record<StepState, string> = {
  done: "已完成",
  failed: "失败",
  running: "进行中",
  pending: "等待",
  skipped: "未开始",
}

/**
 * The list says only what state the request is in; the steps it had belong to
 * the detail, because an upload never fetched anything.
 */
function RequestRow({
  item,
  openPaper,
  onRetry,
  retrying,
}: {
  item: ImportQueueItem
  openPaper: (userPaperId: string) => void
  onRetry: (item: ImportQueueItem) => void
  retrying: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const failed = hasFailed(item)

  return (
    <div className="rounded-lg hover:bg-muted/40">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((before) => !before)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        <StatusIcon item={item} />
        <ChevronRight
          aria-hidden="true"
          className={`size-4 shrink-0 text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`}
        />
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate font-medium">{titleOf(item)}</span>
          {/* The same identifier can be submitted several times: the time is
              what tells those rows apart. */}
          <span className="text-muted-foreground truncate text-xs">
            {submittedAtLabel(item)}
          </span>
        </span>
        <span
          className={`shrink-0 text-xs ${
            failed
              ? "text-destructive"
              : item.status === "success"
                ? "text-success"
                : "text-muted-foreground"
          }`}
        >
          {statusLabel(item)}
        </span>
      </button>

      {expanded && (
        <div className="flex flex-col gap-2 px-3 pb-3 pl-9">
          <ol className="flex flex-col gap-1" aria-label="入库步骤">
            {stepsOf(item).map((step) => (
              <li key={step.key} className="flex items-center gap-2 text-xs">
                <span
                  aria-hidden="true"
                  className={`size-1.5 shrink-0 rounded-full ${STEP_TONE[step.state].dot}`}
                />
                <span className="min-w-0 flex-1">{step.label}</span>
                <span className={STEP_TONE[step.state].text}>
                  {STEP_TEXT[step.state]}
                </span>
              </li>
            ))}
          </ol>
          {reasonOf(item) && (
            <p role="alert" className="text-destructive text-xs">
              {reasonOf(item)}
            </p>
          )}
          <div className="flex items-center gap-3">
            {failed && (
              <Button
                size="sm"
                variant="outline"
                disabled={retrying}
                onClick={() => onRetry(item)}
              >
                {retrying ? (
                  <LoaderCircle data-icon="inline-start" className="animate-spin" />
                ) : (
                  <RotateCw data-icon="inline-start" />
                )}
                重试
              </Button>
            )}
            {item.user_paper_id && !failed && (
              <button
                type="button"
                className="w-fit text-xs underline"
                onClick={() => openPaper(item.user_paper_id!)}
              >
                查看文献
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * What the row is about. A bare number says nothing about which kind of
 * identifier it is, so the kind is always spelled out.
 */
function titleOf(item: ImportQueueItem): string {
  const value = item.identifier
  if (item.identifier_type === "doi") return `DOI: ${value}`
  if (item.identifier_type === "arxiv") return `arxiv_id: ${value}`
  if (item.identifier_type === "upload") {
    return value ? `file_hash: ${value}` : "本地上传"
  }
  return value || "本地上传"
}

/** When this request was submitted, in the reader's own time zone. */
function submittedAtLabel(item: ImportQueueItem): string {
  const submitted = Date.parse(item.created_at)
  if (Number.isNaN(submitted)) return "提交时间未知"
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(submitted))
}

/** A request failed when either its fetch or its processing did. */
function hasFailed(item: ImportQueueItem): boolean {
  return item.status === "failed" || item.run?.status === "failed"
}

/** The backend writes user-readable reasons; show whichever step produced one. */
function reasonOf(item: ImportQueueItem): string | null {
  if (item.status === "failed") return item.error_message ?? "获取原文失败"
  if (item.run?.status === "failed") return item.run.error_message ?? "处理失败"
  return null
}

function statusLabel(item: ImportQueueItem): string {
  // The request is only done when the work it handed over is done too.
  if (item.status !== "success") return STATUS_LABEL[item.status]
  if (item.run?.status === "failed") return STATUS_LABEL.failed
  if (item.run?.status === "success") return STATUS_LABEL.success
  return STATUS_LABEL.running
}

export function ImportQueuePanel() {
  const { open, setOpen, items, loading, error } = useImportQueue()
  const { api } = useApi()
  const queryClient = useQueryClient()
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null)

  function openPaper(userPaperId: string) {
    setOpen(false)
    setSelectedPaperId(userPaperId)
  }

  // Retrying means asking again: the failed record stays as it was, and a new
  // request for the same identifier is queued behind it.
  const retry = useMutation({
    mutationFn: (item: ImportQueueItem) =>
      item.source === "download" && item.identifier
        ? api.imports.start(item.identifier, {
            projectId: item.project_id ?? undefined,
          })
        : Promise.reject(new Error("这次请求没有可重试的标识符，请重新上传文件")),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["import-queue"] })
      notifySuccess("已重新提交")
    },
    onError: (cause) => notifyError(cause),
  })

  return (
    <>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="w-110! max-w-[90vw]! gap-0 p-0">
          <SheetHeader className="border-b px-5 py-4">
            <SheetTitle>入库队列</SheetTitle>
            <SheetDescription>可取用的文献才会出现在文献库</SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            {loading && <p className="text-muted-foreground p-3 text-sm">加载中…</p>}
            {error && <p role="alert" className="text-destructive p-3 text-sm">队列加载失败</p>}
            {!loading && !error && items.length === 0 && (
              <p className="text-muted-foreground p-3 text-sm">暂无入库任务</p>
            )}
            {items.map((item) => (
              <RequestRow
                key={item.id}
                item={item}
                openPaper={openPaper}
                onRetry={(target) => retry.mutate(target)}
                retrying={retry.isPending && retry.variables?.id === item.id}
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
