import { useEffect, useRef, useState } from "react"
import { ChevronLeft, ChevronRight, Minus, Plus } from "lucide-react"
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy, type PDFDocumentLoadingTask } from "pdfjs-dist"
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url"

import { useApi } from "@/lib/api/provider"
import { describeError } from "@/lib/errors"
import { Button } from "@upstream/components/ui/button"
import { Skeleton } from "@upstream/components/ui/skeleton"

GlobalWorkerOptions.workerSrc = workerUrl

export interface PdfTarget {
  page: number
  bbox?: number[] | null
  pageSize?: number[] | null
  coordinateSystem?: "normalized" | "page" | null
}

export function PdfViewer({
  paperId,
  page,
  target,
  className,
}: {
  paperId: string
  page?: number | null
  target?: PdfTarget
  className?: string
}) {
  const { api } = useApi()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null)
  const [currentPage, setCurrentPage] = useState(target?.page ?? page ?? 1)
  const [scale, setScale] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [renderedPage, setRenderedPage] = useState<number | null>(null)
  const [renderedSize, setRenderedSize] = useState<{ width: number; height: number } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    let disposed = false
    let loadingTask: PDFDocumentLoadingTask | null = null
    void (async () => {
      try {
        setDocument(null)
        setError(null)
        const blob = await api.library.pdfBlob(paperId, { signal: controller.signal })
        if (disposed) return
        loadingTask = getDocument({ data: new Uint8Array(await blob.arrayBuffer()) })
        const loaded = await loadingTask.promise
        if (!disposed) {
          setDocument(loaded)
        }
      } catch (cause) {
        if (!disposed) setError(describeError(cause))
      }
    })()
    return () => {
      disposed = true
      controller.abort()
      if (loadingTask) void loadingTask.destroy()
    }
  }, [api, paperId])

  useEffect(() => {
    setCurrentPage(target?.page ?? page ?? 1)
  }, [target, page, paperId])

  const pageNumber = document
    ? Math.min(Math.max(currentPage, 1), document.numPages)
    : currentPage

  useEffect(() => {
    if (!document) return
    let disposed = false
    let renderTask: { promise: Promise<unknown>; cancel: () => void } | null = null
    void (async () => {
      try {
        const pdfPage = await document.getPage(pageNumber)
        if (disposed) return
        const canvas = canvasRef.current
        const context = canvas?.getContext("2d")
        if (!canvas || !context) throw new Error("无法创建 PDF 画布")
        const viewport = pdfPage.getViewport({ scale })
        setRenderedSize({ width: viewport.width, height: viewport.height })
        const pixelRatio = Math.min(window.devicePixelRatio || 1, 2)
        canvas.width = Math.floor(viewport.width * pixelRatio)
        canvas.height = Math.floor(viewport.height * pixelRatio)
        canvas.style.width = `${viewport.width}px`
        canvas.style.height = `${viewport.height}px`
        renderTask = pdfPage.render({
          canvas,
          canvasContext: context,
          viewport,
          transform: pixelRatio === 1 ? undefined : [pixelRatio, 0, 0, pixelRatio, 0, 0],
        })
        await renderTask.promise
        if (!disposed) {
          setRenderedPage(pageNumber)
          setError(null)
        }
      } catch (cause) {
        if (!disposed && !(cause instanceof Error && cause.name === "RenderingCancelledException")) {
          setError(describeError(cause))
        }
      }
    })()
    return () => {
      disposed = true
      renderTask?.cancel()
    }
  }, [document, pageNumber, scale])

  const box = target?.bbox
  const size = target?.pageSize
  const region = box && size && renderedSize && renderedPage === pageNumber && target?.page === pageNumber
    && box.length === 4 && size.length === 2
    && (target?.coordinateSystem === "normalized" || Math.abs(renderedSize.width / renderedSize.height - size[0] / size[1]) < 0.05)
    ? {
        left: `${box[0] / size[0] * 100}%`,
        top: `${box[1] / size[1] * 100}%`,
        width: `${(box[2] - box[0]) / size[0] * 100}%`,
        height: `${(box[3] - box[1]) / size[1] * 100}%`,
      } : null

  if (error) {
    return <div className="text-muted-foreground flex h-full items-center justify-center p-6 text-sm">{error}</div>
  }
  if (!document) {
    return <div className="flex h-full flex-col gap-2 p-6"><Skeleton className="h-6 w-40" /><Skeleton className="h-full w-full" /></div>
  }
  return (
    <div className={className ?? "flex h-full w-full min-h-0 flex-col"}>
      <div className="flex shrink-0 items-center justify-center gap-2 border-b px-2 py-1">
        <Button aria-label="上一页" title="上一页" variant="ghost" size="icon" disabled={pageNumber <= 1} onClick={() => setCurrentPage(pageNumber - 1)}><ChevronLeft /></Button>
        <span className="min-w-16 text-center text-xs tabular-nums">{pageNumber} / {document.numPages}</span>
        <Button aria-label="下一页" title="下一页" variant="ghost" size="icon" disabled={pageNumber >= document.numPages} onClick={() => setCurrentPage(pageNumber + 1)}><ChevronRight /></Button>
        <span className="bg-border mx-1 h-5 w-px" />
        <Button aria-label="缩小" title="缩小" variant="ghost" size="icon" disabled={scale <= 0.5} onClick={() => setScale((value) => Math.max(0.5, value - 0.25))}><Minus /></Button>
        <span className="min-w-9 text-center text-xs tabular-nums">{Math.round(scale * 100)}%</span>
        <Button aria-label="放大" title="放大" variant="ghost" size="icon" disabled={scale >= 3} onClick={() => setScale((value) => Math.min(3, value + 0.25))}><Plus /></Button>
      </div>
      <div className="bg-muted/30 min-h-0 flex-1 overflow-auto p-3">
        <div className="relative mx-auto w-fit shadow-sm">
          <canvas ref={canvasRef} role="img" aria-label="文献原文" className="block bg-white" />
          {region && <div data-testid="pdf-region" aria-label="所选片段位置" className="pointer-events-none absolute rounded-sm border-2 border-amber-500 bg-amber-400/20" style={region} />}
        </div>
      </div>
    </div>
  )
}
