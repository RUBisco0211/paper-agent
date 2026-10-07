import { useInfiniteQuery, useQuery } from "@tanstack/react-query"
import { ArrowLeft, PanelRightClose, PanelRightOpen } from "lucide-react"
import { useEffect, useState } from "react"
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom"

import { PaperDetailSheet } from "@/components/papers/paper-detail-sheet"
import { PdfViewer, type PdfTarget } from "@/components/papers/pdf-viewer"
import { useApi } from "@/lib/api/provider"
import type { PaperBlock } from "@/lib/api/types"
import { describeError } from "@/lib/errors"
import { Button } from "@upstream/components/ui/button"
import { Skeleton } from "@upstream/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@upstream/components/ui/tabs"

const BLOCK_LABELS: Record<string, string> = {
  text: "正文", title: "标题", heading: "标题", table: "表格",
  image: "图片", equation: "公式", formula: "公式", list: "列表",
  code: "代码", reference: "参考文献",
}

function blockLabel(type: string): string {
  return BLOCK_LABELS[type] ?? "其他"
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

  return <div className="flex h-full min-h-0 w-full flex-col">
    <header className="flex min-h-14 items-center gap-3 border-b px-4">
      <Button variant="ghost" size="icon-sm" aria-label="返回" onClick={() => navigate((location.state as { from?: string } | null)?.from ?? "/library")}><ArrowLeft /></Button>
      <div className="min-w-0 flex-1">
        <h1 className="truncate font-medium">{paper.data?.title || paper.data?.original_filename || "文献"}</h1>
        {paper.data && <p className="text-muted-foreground truncate text-xs">{paper.data.authors.join("、") || "作者未知"}{paper.data.year ? ` · ${paper.data.year}` : ""}</p>}
      </div>
      <Button variant="ghost" size="sm" onClick={() => setInfoOpen(true)}>文献信息</Button>
      <Button variant="ghost" size="icon-sm" aria-label={panelOpen ? "收起分块" : "展开分块"} onClick={() => setPanelOpen(!panelOpen)}>{panelOpen ? <PanelRightClose /> : <PanelRightOpen />}</Button>
    </header>
    <div className="flex min-h-0 flex-1">
      <main className="min-w-0 flex-1 overflow-hidden">
        {paper.isPending ? <Skeleton className="m-4 h-[80%]" /> : paper.isError ? <p role="alert" className="p-5 text-sm text-destructive">{describeError(paper.error)}</p> : paper.data?.pdf.available ? <PdfViewer paperId={paperId} target={target} /> : <p className="p-5 text-sm text-muted-foreground">暂无 PDF 原文</p>}
      </main>
      {panelOpen && <aside aria-label="文献分块" className="flex w-80 shrink-0 flex-col overflow-hidden border-l bg-background">
        <div className="border-b px-4 py-3 font-medium">原文片段</div>
        {overview.data?.types.length ? <Tabs value={activeType ?? undefined} onValueChange={(value) => { setSelectedType(value); setSelectedBlock(null) }} className="min-h-0 flex-1">
          <div className="overflow-x-auto border-b px-2">
            <TabsList variant="line" className="w-max">
              {overview.data.types.map((type) => <TabsTrigger key={type} value={type}>{blockLabel(type)}</TabsTrigger>)}
            </TabsList>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {blocks.isError && <p role="alert" className="p-2 text-sm text-destructive">{describeError(blocks.error)}</p>}
            {blocks.data?.pages.flatMap((page) => page.items).map((block) => <button key={block.id} type="button" onClick={() => selectBlock(block)} className={`w-full rounded-md px-3 py-2 text-left hover:bg-muted ${selectedBlock === block.id ? "bg-muted" : ""}`}>
              <span className="text-muted-foreground text-xs">第 {block.page} 页</span>
              <span className="mt-1 line-clamp-4 text-sm whitespace-pre-wrap">{block.text || blockLabel(block.type)}</span>
            </button>)}
            {blocks.hasNextPage && <Button className="mt-2 w-full" variant="ghost" size="sm" disabled={blocks.isFetchingNextPage} onClick={() => void blocks.fetchNextPage()}>加载更多</Button>}
          </div>
        </Tabs> : <p className="p-4 text-sm text-muted-foreground">{overview.isError ? describeError(overview.error) : paper.data?.capabilities.has_fulltext ? "暂无原文片段" : "文献尚未完成解析"}</p>}
      </aside>}
    </div>
    <PaperDetailSheet paperId={infoOpen ? paperId : null} onOpenChange={setInfoOpen} />
  </div>
}
