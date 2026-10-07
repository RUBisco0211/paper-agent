import { useInfiniteQuery, useQuery } from "@tanstack/react-query"
import { ArrowLeft, Copy, Info, Minus, PanelRightClose, PanelRightOpen, Plus, RotateCcw } from "lucide-react"
import { useEffect, useState } from "react"
import katex from "katex"
import "katex/dist/katex.min.css"
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom"

import { PaperDetailSheet } from "@/components/papers/paper-detail-sheet"
import { PdfViewer, type PdfTarget } from "@/components/papers/pdf-viewer"
import { useApi } from "@/lib/api/provider"
import type { PaperBlock } from "@/lib/api/types"
import { describeError, notifyError, notifySuccess } from "@/lib/errors"
import { Button } from "@upstream/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@upstream/components/ui/dialog"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@upstream/components/ui/resizable"
import { Tabs, TabsList, TabsTrigger } from "@upstream/components/ui/tabs"

const BLOCK_LABELS: Record<string, string> = {
  text: "正文", title: "标题", heading: "小标题", table: "表格",
  image: "图片", equation: "公式", formula: "公式块", equation_interline: "独立公式",
  list: "列表", code: "代码", reference: "参考文献", chart: "图表",
  header: "页眉", footer: "页脚", page_number: "页码", aside_text: "边注",
  page_footnote: "脚注", ref_text: "参考条目",
}

function blockLabel(type: string): string {
  return BLOCK_LABELS[type] ?? type
}

function formulaMarkup(formula: string): string | null {
  try {
    return katex.renderToString(normalizeFormula(formula), { displayMode: true, throwOnError: true, trust: false })
  } catch {
    return null
  }
}

function normalizeFormula(formula: string): string {
  const text = formula.trim()
  if (text.startsWith("$$") && text.endsWith("$$")) return text.slice(2, -2).trim()
  if (text.startsWith("\\[") && text.endsWith("\\]")) return text.slice(2, -2).trim()
  if (text.startsWith("\\(") && text.endsWith("\\)")) return text.slice(2, -2).trim()
  if (text.startsWith("$") && text.endsWith("$")) return text.slice(1, -1).trim()
  return text
}

function BlockImagePreview({ paperId, block, onOpen }: {
  paperId: string
  block: PaperBlock
  onOpen?: (source: string) => void
}) {
  const { api } = useApi()
  const [source, setSource] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    let objectUrl: string | null = null
    setSource(null)
    setFailed(false)
    void api.library.blockImageBlob(paperId, block.id, { signal: controller.signal })
      .then((blob) => {
        if (controller.signal.aborted) return
        objectUrl = URL.createObjectURL(blob)
        setSource(objectUrl)
      })
      .catch(() => { if (!controller.signal.aborted) setFailed(true) })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [api, paperId, block.id])
  if (failed) return <span className="text-muted-foreground text-xs">图片预览不可用</span>
  if (!source) return <span className="bg-muted block h-24 animate-pulse rounded-sm" />
  const image = <img src={source} alt={block.text || "图片预览"} className="max-h-48 w-full rounded-sm object-contain" />
  return onOpen
    ? <button type="button" aria-label={block.type === "chart" ? "查看图表" : "查看图片"} className="w-full cursor-zoom-in" onClick={() => onOpen(source)}>{image}</button>
    : image
}

export function PaperReadingPage() {
  const { paperId = "" } = useParams()
  const { api } = useApi()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const initialPage = Number(searchParams.get("page"))
  const linkedBlockId = Number(searchParams.get("block"))
  const [target, setTarget] = useState<PdfTarget | undefined>(
    Number.isSafeInteger(initialPage) && initialPage > 0 ? { page: initialPage } : undefined,
  )
  const [selectedBlock, setSelectedBlock] = useState<number | null>(null)
  const [selectedType, setSelectedType] = useState<string | null>(null)
  const [panelOpen, setPanelOpen] = useState(true)
  const [infoOpen, setInfoOpen] = useState(false)
  const [imageViewer, setImageViewer] = useState<{ source: string; title: string } | null>(null)
  const [imageZoom, setImageZoom] = useState(1)

  const paper = useQuery({
    queryKey: ["paper", paperId],
    queryFn: () => api.library.detail(paperId),
    enabled: Boolean(paperId),
  })
  const overview = useQuery({
    queryKey: ["paper-blocks", paperId, "types"],
    queryFn: () => api.library.blocks(paperId, { limit: 1 }),
    enabled: Boolean(paperId && paper.data?.capabilities.has_fulltext),
  })
  const linkedBlock = useQuery({
    queryKey: ["paper-block", paperId, linkedBlockId],
    queryFn: () => api.library.block(paperId, linkedBlockId),
    enabled: Boolean(paperId && Number.isSafeInteger(linkedBlockId) && linkedBlockId >= 0 && searchParams.has("block")),
  })
  useEffect(() => {
    if (!linkedBlock.data) return
    setSelectedBlock(linkedBlock.data.id)
    setSelectedType(linkedBlock.data.type)
    setTarget({
      page: linkedBlock.data.page,
      bbox: linkedBlock.data.bbox,
      pageSize: linkedBlock.data.page_size,
      coordinateSystem: linkedBlock.data.coordinate_system,
    })
  }, [linkedBlock.data])
  const activeType = selectedType ?? overview.data?.types[0] ?? null
  const blocks = useInfiniteQuery({
    queryKey: ["paper-blocks", paperId, activeType],
    queryFn: ({ pageParam }) => api.library.blocks(paperId, {
      type: activeType ?? undefined, offset: pageParam, limit: 50,
    }),
    initialPageParam: 0,
    getNextPageParam: (last) =>
      last.offset + last.items.length < last.total ? last.offset + last.items.length : undefined,
    enabled: Boolean(paperId && activeType && panelOpen),
  })

  function selectBlock(block: PaperBlock) {
    setSelectedBlock(block.id)
    setTarget({
      page: block.page,
      bbox: block.bbox,
      pageSize: block.page_size,
      coordinateSystem: block.coordinate_system,
    })
    setSearchParams({ page: String(block.page), block: String(block.id) }, { replace: true })
  }

  async function copyBlock(block: PaperBlock) {
    try {
      await navigator.clipboard.writeText(block.formula ? normalizeFormula(block.formula) : block.text)
      notifySuccess("已复制")
    } catch (error) {
      notifyError(error, "复制失败")
    }
  }

  return <div className="flex h-full min-h-0 w-full flex-col">
    <header className="flex min-h-14 items-center gap-3 border-b px-4">
      <Button variant="ghost" size="icon-sm" aria-label="返回" onClick={() => navigate((location.state as { from?: string } | null)?.from ?? "/library")}><ArrowLeft /></Button>
      <div className="min-w-0 flex-1">
        <h1 className="truncate font-medium">{paper.data?.title || paper.data?.original_filename || "文献"}</h1>
        {paper.data && <p className="text-muted-foreground truncate text-xs">{paper.data.authors.join("、") || "作者未知"}{paper.data.year ? ` · ${paper.data.year}` : ""}</p>}
      </div>
      <Button variant="ghost" size="icon-sm" aria-label="文献信息" title="文献信息" onClick={() => setInfoOpen(true)}><Info /></Button>
      <Button variant="ghost" size="icon-sm" aria-label={panelOpen ? "收起分块" : "展开分块"} onClick={() => { setPanelOpen(!panelOpen); setImageViewer(null) }}>{panelOpen ? <PanelRightClose /> : <PanelRightOpen />}</Button>
    </header>
    <ResizablePanelGroup orientation="horizontal" className="min-h-0 flex-1">
      <ResizablePanel minSize="20rem" className="min-h-0 min-w-0">
        <main className="h-full min-w-0 overflow-hidden">
        {paper.isError ? <p role="alert" className="p-5 text-sm text-destructive">{describeError(paper.error)}</p> : paper.data && !paper.data.pdf.available ? <p className="p-5 text-sm text-muted-foreground">暂无 PDF 原文</p> : <PdfViewer paperId={paperId} target={target} />}
        </main>
      </ResizablePanel>
      {panelOpen && <>
        <ResizableHandle aria-label="调整分块宽度" withHandle />
        <ResizablePanel defaultSize="26rem" minSize="20rem" maxSize="50rem" className="min-h-0 min-w-0">
          <aside aria-label="文献分块" className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
        {overview.data?.types.length ? <Tabs value={activeType ?? undefined} onValueChange={(value) => { setSelectedType(value); setSelectedBlock(null); setImageViewer(null) }} className="h-full min-h-0 flex-1 gap-0">
          <div className="flex h-12 shrink-0 items-center overflow-x-auto border-b px-2">
            <TabsList variant="line" className="w-max">
              {overview.data.types.map((type) => <TabsTrigger key={type} value={type}>{blockLabel(type)}</TabsTrigger>)}
            </TabsList>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {blocks.isError && <p role="alert" className="p-2 text-sm text-destructive">{describeError(blocks.error)}</p>}
            {blocks.data?.pages.flatMap((page) => page.items).map((block) => {
              const isFormula = block.type === "equation" || block.type === "formula" || block.type === "equation_interline"
              const markup = isFormula && block.formula ? formulaMarkup(block.formula) : null
              const canCopy = (block.type === "text" && Boolean(block.text)) || (isFormula && Boolean(block.formula || block.text))
              return <div key={block.id} className={`relative rounded-md hover:bg-muted ${selectedBlock === block.id ? "bg-muted" : ""}`}>
                <button type="button" onClick={() => selectBlock(block)} className="w-full px-3 py-2 text-left">
                  <span className="text-muted-foreground text-xs">第 {block.page} 页</span>
                  <span className="mt-1 block">
                    {markup ? <span className="block max-w-full overflow-x-auto text-sm" dangerouslySetInnerHTML={{ __html: markup }} /> : null}
                    {block.text && (!markup || block.type === "image" || block.type === "chart") && <span className="line-clamp-4 text-sm whitespace-pre-wrap">{isFormula && block.formula ? normalizeFormula(block.formula) : block.text}</span>}
                    {!block.text && !markup && !block.has_image && <span className="text-muted-foreground text-sm">{blockLabel(block.type)}</span>}
                  </span>
                </button>
                {block.has_image && (block.type === "image" || block.type === "chart" || (isFormula && !block.formula)) && <div className="px-3 pb-2">
                  <BlockImagePreview paperId={paperId} block={block} onOpen={block.type === "image" || block.type === "chart" ? (source) => { setImageViewer({ source, title: block.type === "chart" ? "图表预览" : "图片预览" }); setImageZoom(1) } : undefined} />
                </div>}
                {canCopy && <Button variant="ghost" size="icon-sm" className="absolute right-1 top-1" aria-label={isFormula ? "复制公式" : "复制正文"} title={isFormula ? "复制公式" : "复制正文"} onClick={() => void copyBlock(block)}><Copy /></Button>}
              </div>
            })}
            {blocks.hasNextPage && <Button className="mt-2 w-full" variant="ghost" size="sm" disabled={blocks.isFetchingNextPage} onClick={() => void blocks.fetchNextPage()}>加载更多</Button>}
          </div>
        </Tabs> : <p className="p-4 text-sm text-muted-foreground">{overview.isError ? describeError(overview.error) : paper.data?.capabilities.has_fulltext ? "暂无原文片段" : "文献尚未完成解析"}</p>}
          </aside>
        </ResizablePanel>
      </>}
    </ResizablePanelGroup>
    <PaperDetailSheet paperId={infoOpen ? paperId : null} onOpenChange={setInfoOpen} />
    <Dialog open={Boolean(imageViewer)} onOpenChange={(open) => { if (!open) setImageViewer(null) }}>
      <DialogContent className="flex h-[92vh] w-[96vw] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none">
        <div className="flex h-12 shrink-0 items-center gap-2 border-b px-4 pr-12">
          <DialogTitle className="min-w-0 flex-1 truncate">{imageViewer?.title}</DialogTitle>
          <DialogDescription className="sr-only">放大或缩小图片以查看细节</DialogDescription>
          <Button variant="ghost" size="icon-sm" aria-label="缩小图片" disabled={imageZoom <= 0.5} onClick={() => setImageZoom((value) => Math.max(0.5, value - 0.25))}><Minus /></Button>
          <span className="min-w-10 text-center text-xs tabular-nums">{Math.round(imageZoom * 100)}%</span>
          <Button variant="ghost" size="icon-sm" aria-label="放大图片" disabled={imageZoom >= 4} onClick={() => setImageZoom((value) => Math.min(4, value + 0.25))}><Plus /></Button>
          <Button variant="ghost" size="icon-sm" aria-label="重置缩放" onClick={() => setImageZoom(1)}><RotateCcw /></Button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-muted/30 p-4">
          <div className="flex min-h-full min-w-full items-center justify-center">
            {imageViewer && <img src={imageViewer.source} alt={imageViewer.title} className="h-auto shrink-0 object-contain" style={{ width: imageZoom === 1 ? "auto" : `${imageZoom * 90}vw`, maxWidth: imageZoom === 1 ? "100%" : "none", maxHeight: imageZoom === 1 ? "calc(92vh - 5rem)" : "none" }} />}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  </div>
}
