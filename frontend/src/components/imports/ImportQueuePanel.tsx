import { LoaderCircle } from "lucide-react"
import { useState } from "react"

import { PaperDetailSheet } from "@/components/papers/PaperDetailSheet"
import { useImportQueue } from "@/components/providers/ImportQueueProvider"
import { importQueueLabel } from "@/lib/papers/vocabulary"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/Sheet"
import type { ImportQueueItem } from "@/types/business"

const stageColors: Record<string, string> = {
  metadata: "text-info", fulltext: "text-info", chunking: "text-info",
  embedding: "text-info", failed: "text-destructive", ready: "text-success",
  succeeded: "text-success", pdf_unavailable: "text-warning",
}

function QueueRow({ item, openPaper }: { item: ImportQueueItem; openPaper: (paperId: string) => void }) {
  const active = ["queued", "running", "resolving", "downloading", "metadata_ready"].includes(item.status)
  const stage = item.stage ?? item.status
  const content = <>
    <span className="min-w-0 flex-1 truncate font-medium">{item.title || item.identifier || "文献处理"}</span>
    {active && <LoaderCircle aria-label="处理中" className="size-4 shrink-0 animate-spin" />}
    <span className={`shrink-0 text-xs ${stageColors[stage] ?? "text-muted-foreground"}`}>{importQueueLabel(stage)}</span>
  </>
  return item.paper_id
    ? <button type="button" onClick={() => openPaper(item.paper_id!)} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left hover:bg-muted">{content}</button>
    : <div className="flex items-center gap-2 px-3 py-2">{content}</div>
}

export function ImportQueuePanel() {
  const { open, setOpen, items, loading, error } = useImportQueue()
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null)
  function openPaper(paperId: string) {
    setOpen(false)
    setSelectedPaperId(paperId)
  }
  return <><Sheet open={open} onOpenChange={setOpen}>
    <SheetContent side="right" className="w-110! max-w-[90vw]! gap-0 p-0">
      <SheetHeader className="border-b px-5 py-4"><SheetTitle>入库队列</SheetTitle>
        <SheetDescription>仅显示你的导入与文献处理任务</SheetDescription></SheetHeader>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {loading && <p className="p-3 text-sm text-muted-foreground">加载中…</p>}
        {error && <p role="alert" className="p-3 text-sm text-destructive">队列加载失败</p>}
        {!loading && !error && items.length === 0 && <p className="p-3 text-sm text-muted-foreground">暂无入库任务</p>}
        {items.map((item) => <QueueRow key={`${item.kind}:${item.id}`} item={item} openPaper={openPaper} />)}
      </div>
    </SheetContent>
  </Sheet><PaperDetailSheet paperId={selectedPaperId} onOpenChange={(nextOpen) => { if (!nextOpen) setSelectedPaperId(null) }} /></>
}
