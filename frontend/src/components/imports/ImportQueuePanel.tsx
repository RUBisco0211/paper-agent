import { ChevronRight, LoaderCircle } from "lucide-react"
import { useState } from "react"

import { PaperDetailSheet } from "@/components/papers/PaperDetailSheet"
import { useImportQueue } from "@/components/providers/ImportQueueProvider"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/Sheet"
import type { DownloadStatus, ImportQueueItem, RunStatus } from "@/types/business"

const STATUS_LABEL: Record<DownloadStatus, string> = {
  pending: "等待中",
  running: "处理中",
  success: "已完成",
  failed: "失败",
}

/**
 * The list says only what state the request is in. Which steps it had — a
 * fetch, then parsing, chunking and embedding — belongs to the detail, because
 * an upload never fetched anything and there is no point showing the difference
 * up front.
 */
function RequestRow({
  item,
  openPaper,
}: {
  item: ImportQueueItem
  openPaper: (paperId: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const label = statusLabel(item)
  const busy = item.status === "pending" || item.status === "running"

  return (
    <div className="rounded-lg hover:bg-muted/40">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((before) => !before)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        <ChevronRight
          aria-hidden="true"
          className={`size-4 shrink-0 text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`}
        />
        <span className="min-w-0 flex-1 truncate font-medium">
          {item.identifier || "本地上传"}
        </span>
        {busy && <LoaderCircle aria-label="进行中" className="size-4 shrink-0 animate-spin" />}
        <span
          className={`shrink-0 text-xs ${
            item.status === "failed"
              ? "text-destructive"
              : item.status === "success"
                ? "text-success"
                : "text-muted-foreground"
          }`}
        >
          {label}
        </span>
      </button>

      {expanded && (
        <div className="flex flex-col gap-2 px-3 pb-3 pl-9">
          <ol className="flex flex-col gap-1" aria-label="入库步骤">
            {stepsOf(item).map((step) => (
              <li key={step.label} className="flex items-center gap-2 text-xs">
                <span
                  aria-hidden="true"
                  className={`size-1.5 rounded-full ${
                    step.state === "failed"
                      ? "bg-destructive"
                      : step.state === "done"
                        ? "bg-success"
                        : "bg-muted-foreground"
                  }`}
                />
                <span className="min-w-0 flex-1">{step.label}</span>
                <span className="text-muted-foreground">{step.text}</span>
              </li>
            ))}
          </ol>
          {item.error_message && (
            <p className="text-destructive text-xs">{item.error_message}</p>
          )}
          {item.paper_id && item.status === "success" && (
            <button
              type="button"
              className="w-fit text-xs underline"
              onClick={() => openPaper(item.paper_id!)}
            >
              查看文献
            </button>
          )}
        </div>
      )}
    </div>
  )
}

type StepState = "done" | "failed" | "pending"

function stepsOf(item: ImportQueueItem): Array<{ label: string; state: StepState; text: string }> {
  const steps: Array<{ label: string; state: StepState; text: string }> = []
  // Only a request that had to fetch shows a fetching step at all.
  if (item.source === "download") {
    steps.push({
      label: "获取原文",
      state:
        item.status === "success"
          ? "done"
          : item.status === "failed"
            ? "failed"
            : "pending",
      text: item.status === "success" ? "已完成" : item.status === "failed" ? "失败" : "进行中",
    })
  } else {
    steps.push({ label: "文件上传", state: "done", text: "已完成" })
  }
  const run = item.run
  if (run) {
    steps.push({
      label: stageLabel(run.stage),
      state: run.status === "success" ? "done" : run.status === "failed" ? "failed" : "pending",
      text: runText(run.status),
    })
  }
  return steps
}

function stageLabel(stage?: string | null): string {
  if (stage === "parse") return "解析正文"
  if (stage === "chunk") return "切分片段"
  if (stage === "embed") return "生成向量"
  return "处理文献"
}

function runText(status: RunStatus): string {
  if (status === "success") return "已完成"
  if (status === "failed") return "失败"
  return "进行中"
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
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null)

  function openPaper(paperId: string) {
    setOpen(false)
    setSelectedPaperId(paperId)
  }

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
              <RequestRow key={item.id} item={item} openPaper={openPaper} />
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
