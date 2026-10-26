import { Check, Circle, LoaderCircle, X } from "lucide-react"
import { useState } from "react"

import { PaperDetailSheet } from "@/components/papers/PaperDetailSheet"
import { useImportQueue } from "@/components/providers/ImportQueueProvider"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/Sheet"
import type { DownloadStatus, ImportQueueItem, RunStatus } from "@/types/business"

const DOWNLOAD_LABEL: Record<DownloadStatus, string> = {
  pending: "等待获取",
  running: "正在获取原文",
  success: "原文已获取",
  failed: "获取原文失败",
}

const RUN_LABEL: Record<RunStatus, string> = {
  pending: "等待处理",
  running: "正在处理",
  success: "已完成",
  failed: "处理失败",
}

const STAGE_LABEL: Record<string, string> = {
  parse: "解析正文",
  chunk: "切分片段",
  embed: "生成向量",
}

/**
 * One request reads as one process: fetching the file, then processing it.
 * A failed fetch stops there, so no processing stage is shown for it.
 */
function QueueRow({
  item,
  openPaper,
}: {
  item: ImportQueueItem
  openPaper: (paperId: string) => void
}) {
  const active = item.status === "pending" || item.status === "running"
  const title = item.identifier || "文献入库"
  const run = item.run
  const reason = item.error_message ?? run?.error_message

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
      </div>

      <ol className="flex flex-wrap gap-x-4 gap-y-1 pl-1" aria-label="入库进度">
        <Step
          label="获取原文"
          state={
            item.status === "failed"
              ? "failed"
              : item.status === "success"
                ? "done"
                : "running"
          }
        />
        {run && (
          <Step
            label={STAGE_LABEL[run.stage ?? ""] ?? "处理文献"}
            state={
              run.status === "failed"
                ? "failed"
                : run.status === "success"
                  ? "done"
                  : "running"
            }
          />
        )}
      </ol>

      <p className="text-muted-foreground text-xs">
        {run && item.status === "success" ? RUN_LABEL[run.status] : DOWNLOAD_LABEL[item.status]}
      </p>

      {reason && <p className="text-destructive text-xs">{reason}</p>}
    </div>
  )
}

function Step({ label, state }: { label: string; state: "done" | "failed" | "running" }) {
  const Icon = state === "failed" ? X : state === "done" ? Check : Circle
  return (
    <li
      className={`flex items-center gap-1 text-xs ${
        state === "failed"
          ? "text-destructive"
          : state === "done"
            ? "text-success"
            : "text-primary"
      }`}
    >
      <Icon aria-hidden="true" className="size-3" />
      {label}
    </li>
  )
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
              <QueueRow key={item.id} item={item} openPaper={openPaper} />
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
