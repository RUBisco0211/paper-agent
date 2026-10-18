import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type RefObject } from "react"
import { useQuery } from "@tanstack/react-query"
import { ChevronLeft, ChevronRight, Copy, MessageSquarePlus, Minus, Plus } from "lucide-react"
import { getDocument, GlobalWorkerOptions, TextLayer, type PDFDocumentProxy, type PDFDocumentLoadingTask } from "pdfjs-dist"
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url"

import { useApi } from "@/components/providers/ApiProvider"
import { describeError, notifyError, notifySuccess } from "@/lib/errors"
import { Button } from "@/components/ui/Button"
import { Skeleton } from "@/components/ui/Skeleton"

GlobalWorkerOptions.workerSrc = workerUrl

export interface PdfTarget {
  page: number
  bbox?: number[] | null
  pageSize?: number[] | null
  coordinateSystem?: "normalized" | "page" | null
  rects?: number[][]
}

export function PdfViewer({
  paperId,
  page,
  target,
  onClearTarget,
  onQuoteSelection,
  className,
}: {
  paperId: string
  page?: number | null
  target?: PdfTarget
  onClearTarget?: () => void
  onQuoteSelection?: (selection: { page: number; text: string; rects: number[][] }) => void
  className?: string
}) {
  const { api } = useApi()
  const pdfBytes = useQuery({
    queryKey: ["paper-pdf", paperId],
    queryFn: ({ signal }) => api.library.pdfBlob(paperId, { signal }),
    staleTime: 60_000,
    gcTime: 5 * 60_000,
    enabled: Boolean(paperId),
  })
  const scrollRef = useRef<HTMLDivElement>(null)
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map())
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null)
  const [currentPage, setCurrentPage] = useState(target?.page ?? page ?? 1)
  const [scale, setScale] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; text: string; page?: number; rects?: number[][] } | null>(null)

  useEffect(() => {
    const element = scrollRef.current
    if (!element) return
    function handleWheel(event: WheelEvent) {
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault()
        setScale((value) => Math.min(3, Math.max(0.5, value + (event.deltaY < 0 ? 0.25 : -0.25))))
      } else if (event.shiftKey && element) {
        event.preventDefault()
        element.scrollLeft += event.deltaY || event.deltaX
      }
    }
    element.addEventListener("wheel", handleWheel, { passive: false })
    return () => element.removeEventListener("wheel", handleWheel)
  }, [document])

  useEffect(() => {
    let disposed = false
    let loadingTask: PDFDocumentLoadingTask | null = null
    void (async () => {
      try {
        setDocument(null)
        setError(null)
        pageRefs.current.clear()
        const blob = pdfBytes.data
        if (!blob) return
        if (disposed) return
        loadingTask = getDocument({ data: new Uint8Array(await blob.arrayBuffer()) })
        const loaded = await loadingTask.promise
        if (!disposed) setDocument(loaded)
      } catch (cause) {
        if (!disposed) setError(describeError(cause))
      }
    })()
    return () => {
      disposed = true
      if (loadingTask) void loadingTask.destroy()
    }
  }, [paperId, pdfBytes.data])

  useEffect(() => {
    if (!document || (!target && !page)) return
    const requested = Math.min(Math.max(target?.page ?? page ?? 1, 1), document.numPages)
    setCurrentPage(requested)
    pageRefs.current.get(requested)?.scrollIntoView?.({ block: "start" })
  }, [document, target, page, paperId])

  function goToPage(requested: number) {
    if (!document) return
    const next = Math.min(Math.max(requested, 1), document.numPages)
    setCurrentPage(next)
    pageRefs.current.get(next)?.scrollIntoView?.({ behavior: "smooth", block: "start" })
  }

  function trackScroll() {
    setContextMenu(null)
    const root = scrollRef.current
    if (!root) return
    const top = root.getBoundingClientRect().top + 16
    let closest = currentPage
    let distance = Number.POSITIVE_INFINITY
    for (const [number, element] of pageRefs.current) {
      const delta = Math.abs(element.getBoundingClientRect().top - top)
      if (delta < distance) {
        distance = delta
        closest = number
      }
    }
    if (closest !== currentPage) setCurrentPage(closest)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if ((event.ctrlKey || event.metaKey) && (event.key === "+" || event.key === "=" || event.key === "-")) {
      event.preventDefault()
      setScale((value) => Math.min(3, Math.max(0.5, value + (event.key === "-" ? -0.25 : 0.25))))
    } else if (event.shiftKey && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
      event.preventDefault()
      event.currentTarget.scrollLeft += event.key === "ArrowLeft" ? -80 : 80
    }
  }

  function showTextMenu(event: MouseEvent<HTMLDivElement>) {
    const selection = window.getSelection()
    const root = scrollRef.current
    const text = selection?.toString().trim()
    if (!selection || !text || !root || !selection.anchorNode || !root.contains(selection.anchorNode)) return
    const anchor = selection.anchorNode instanceof Element ? selection.anchorNode : selection.anchorNode.parentElement
    const focus = selection.focusNode instanceof Element ? selection.focusNode : selection.focusNode?.parentElement
    const pageElement = anchor?.closest<HTMLElement>("[data-paper-pdf-page]")
    const samePage = pageElement && pageElement === focus?.closest("[data-paper-pdf-page]")
    const page = samePage ? Number(pageElement.dataset.pageNumber) : undefined
    const bounds = pageElement?.getBoundingClientRect()
    const rects = samePage && bounds && bounds.width && bounds.height
      ? Array.from(selection.getRangeAt(0).getClientRects()).map((rect) => [
          (rect.left - bounds.left) / bounds.width, (rect.top - bounds.top) / bounds.height,
          (rect.right - bounds.left) / bounds.width, (rect.bottom - bounds.top) / bounds.height,
        ]) : undefined
    event.preventDefault()
    setContextMenu({
      x: Math.max(8, Math.min(event.clientX, window.innerWidth - 112)),
      y: Math.max(8, Math.min(event.clientY, window.innerHeight - (onQuoteSelection ? 88 : 48))),
      text, page: Number.isSafeInteger(page) && page! > 0 ? page : undefined, rects,
    })
  }

  function clearTargetFromBlank(event: MouseEvent<HTMLDivElement>) {
    if (!target || !onClearTarget || window.getSelection()?.toString().trim()) return
    const element = event.target
    if (!(element instanceof HTMLElement)) return
    if (element === event.currentTarget || element.matches("canvas, .paper-pdf-text-layer, [data-paper-pdf-page]")) onClearTarget()
  }

  async function copySelectedText() {
    if (!contextMenu) return
    try {
      await navigator.clipboard.writeText(contextMenu.text)
      notifySuccess("已复制")
    } catch (cause) {
      notifyError(cause, "复制失败")
    } finally {
      setContextMenu(null)
    }
  }

  if (error || pdfBytes.isError) return <div className="text-muted-foreground flex h-full items-center justify-center p-6 text-sm">{error ?? describeError(pdfBytes.error)}</div>
  if (!document) return <div className="flex h-full flex-col gap-2 p-6"><Skeleton className="h-6 w-40" /><Skeleton className="h-full w-full" /></div>

  return <div className={className ?? "flex h-full w-full min-h-0 flex-col"}>
    <div className="flex h-12 shrink-0 items-center justify-center gap-2 border-b px-2">
      <Button aria-label="上一页" title="上一页" variant="ghost" size="icon" disabled={currentPage <= 1} onClick={() => goToPage(currentPage - 1)}><ChevronLeft /></Button>
      <span className="min-w-16 text-center text-xs tabular-nums">{currentPage} / {document.numPages}</span>
      <Button aria-label="下一页" title="下一页" variant="ghost" size="icon" disabled={currentPage >= document.numPages} onClick={() => goToPage(currentPage + 1)}><ChevronRight /></Button>
      <span className="bg-border mx-1 h-5 w-px" />
      <Button aria-label="缩小" title="缩小（Ctrl/⌘ + 滚轮）" variant="ghost" size="icon" disabled={scale <= 0.5} onClick={() => setScale((value) => Math.max(0.5, value - 0.25))}><Minus /></Button>
      <span className="min-w-9 text-center text-xs tabular-nums">{Math.round(scale * 100)}%</span>
      <Button aria-label="放大" title="放大（Ctrl/⌘ + 滚轮）" variant="ghost" size="icon" disabled={scale >= 3} onClick={() => setScale((value) => Math.min(3, value + 0.25))}><Plus /></Button>
    </div>
    <div ref={scrollRef} role="region" aria-label="PDF 页面" tabIndex={0} onScroll={trackScroll} onKeyDown={handleKeyDown} onContextMenu={showTextMenu} onClick={clearTargetFromBlank} className="bg-muted/30 min-h-0 flex-1 overflow-auto p-3">
      <div className="flex min-w-full w-max flex-col items-center gap-4">
        {Array.from({ length: document.numPages }, (_, index) => {
          const number = index + 1
          return <PdfPageCanvas key={number} document={document} number={number} scale={scale} target={target?.page === number ? target : undefined} rootRef={scrollRef} pageRef={(element) => {
            if (element) pageRefs.current.set(number, element)
            else pageRefs.current.delete(number)
          }} />
        })}
      </div>
    </div>
    {contextMenu && <>
      <div className="fixed inset-0 z-40" onClick={() => setContextMenu(null)} />
      <div role="menu" aria-label="文本操作" className="bg-popover text-popover-foreground fixed z-50 min-w-24 rounded-md border p-1 shadow-lg" style={{ left: contextMenu.x, top: contextMenu.y }}>
        <Button role="menuitem" variant="ghost" size="sm" className="w-full justify-start" onClick={() => void copySelectedText()}><Copy />复制</Button>
        {onQuoteSelection && contextMenu.page && <Button role="menuitem" variant="ghost" size="sm" className="w-full justify-start" onClick={() => {
          onQuoteSelection({ page: contextMenu.page!, text: contextMenu.text, rects: contextMenu.rects ?? [] })
          setContextMenu(null)
        }}><MessageSquarePlus />添加到对话</Button>}
      </div>
    </>}
  </div>
}

function PdfPageCanvas({ document, number, scale, target, rootRef, pageRef }: {
  document: PDFDocumentProxy
  number: number
  scale: number
  target?: PdfTarget
  rootRef: RefObject<HTMLDivElement | null>
  pageRef: (element: HTMLDivElement | null) => void
}) {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const textLayerRef = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(() => typeof IntersectionObserver === "undefined")
  const [size, setSize] = useState({ width: 612, height: 792 })
  const [rendered, setRendered] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const element = wrapperRef.current
    if (!element || typeof IntersectionObserver === "undefined") return
    const observer = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting),
      { root: rootRef.current, rootMargin: "200px" },
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [rootRef])

  useEffect(() => {
    if (!visible) return
    let disposed = false
    let renderTask: { promise: Promise<unknown>; cancel: () => void } | null = null
    let textLayer: TextLayer | null = null
    void (async () => {
      try {
        setRendered(false)
        const pdfPage = await document.getPage(number)
        if (disposed) return
        const canvas = canvasRef.current
        const textContainer = textLayerRef.current
        const context = canvas?.getContext("2d")
        if (!canvas || !context || !textContainer) throw new Error("无法创建 PDF 画布")
        const viewport = pdfPage.getViewport({ scale })
        setSize({ width: viewport.width, height: viewport.height })
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
          setRendered(true)
          setError(null)
        }
        const textContent = await pdfPage.getTextContent()
        if (disposed) return
        textContainer.replaceChildren()
        textContainer.style.setProperty("--total-scale-factor", String(viewport.scale))
        textLayer = new TextLayer({ textContentSource: textContent, container: textContainer, viewport })
        await textLayer.render()
      } catch (cause) {
        if (!disposed && !(cause instanceof Error && cause.name === "RenderingCancelledException")) {
          setError(describeError(cause))
        }
      }
    })()
    return () => {
      disposed = true
      renderTask?.cancel()
      textLayer?.cancel()
    }
  }, [document, number, scale, visible])

  const box = target?.bbox
  const sourceSize = target?.pageSize
  const region = visible && rendered && box && sourceSize && box.length === 4 && sourceSize.length === 2
    && (target?.coordinateSystem === "normalized" || Math.abs(size.width / size.height - sourceSize[0] / sourceSize[1]) < 0.05)
    ? {
        left: `${box[0] / sourceSize[0] * 100}%`,
        top: `${box[1] / sourceSize[1] * 100}%`,
        width: `${(box[2] - box[0]) / sourceSize[0] * 100}%`,
        height: `${(box[3] - box[1]) / sourceSize[1] * 100}%`,
      } : null
  const quoteRegions = visible && rendered ? (target?.rects ?? []).filter((rect) =>
    rect.length === 4 && rect.every((value) => Number.isFinite(value) && value >= 0 && value <= 1) &&
    rect[2] > rect[0] && rect[3] > rect[1],
  ) : []

  return <div data-paper-pdf-page data-page-number={number} ref={(element) => { wrapperRef.current = element; pageRef(element) }} className="relative shrink-0 bg-white shadow-sm" style={{ width: size.width, minHeight: size.height }}>
    {visible && <canvas ref={canvasRef} role="img" aria-label="文献原文" className="block bg-white" />}
    {visible && <div ref={textLayerRef} className="paper-pdf-text-layer" />}
    {error && <p role="alert" className="p-4 text-sm text-destructive">第 {number} 页无法显示：{error}</p>}
    {region && <div data-testid="pdf-region" aria-label="所选片段位置" className="paper-pdf-location pointer-events-none absolute" style={region} />}
    {quoteRegions.map((rect, index) => <div key={index} aria-label="引用文本位置" className="paper-pdf-quote pointer-events-none absolute" style={{ left: `${rect[0] * 100}%`, top: `${rect[1] * 100}%`, width: `${(rect[2] - rect[0]) * 100}%`, height: `${(rect[3] - rect[1]) * 100}%` }} />)}
  </div>
}
