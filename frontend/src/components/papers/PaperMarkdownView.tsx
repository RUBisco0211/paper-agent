import { useQuery } from "@tanstack/react-query"
import { useVirtualizer } from "@tanstack/react-virtual"
import { MessageSquarePlus } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"

import { Markdown } from "@/components/markdown/Markdown"
import { useApi } from "@/components/providers/ApiProvider"
import { Button } from "@/components/ui/Button"
import { isApiError } from "@/lib/api/errors"
import { describeError, notifyError } from "@/lib/errors"
import type { PaperQuote } from "@/types/chat"

/** How much source text one page of the virtualized reader holds. */
const PAGE_CHARS = 4000

const IMAGE_LINK = /(!\[[^\]]*\]\()(?:\.\/)?(images\/[^\s)]+)(\s+"[^"]*")?(\))/g

/** Point the markdown's relative image links at the paper's asset endpoint. */
function linkImages(markdown: string, url: (path: string) => string): string {
  return markdown.replace(
    IMAGE_LINK,
    (_match, head: string, path: string, title = "", tail: string) =>
      `${head}${url(path)}${title}${tail}`,
  )
}

function assetPath(source: string | undefined): string | null {
  if (!source) return null
  const path = source.split("/assets/")[1]
  if (!path || !path.startsWith("images/") || path.includes("..")) return null
  return path
}

function MarkdownImage({ paperId, source, alt }: {
  paperId: string
  source?: string
  alt?: string
}) {
  const { api } = useApi()
  const path = assetPath(source)
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  // Only pages near the viewport are mounted, so this runs for a few figures.
  useEffect(() => {
    if (!path) return
    const controller = new AbortController()
    let objectUrl: string | null = null
    setFailed(false)
    void api.library.assetBlob(paperId, path, { signal: controller.signal })
      .then((blob) => {
        if (controller.signal.aborted) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => { if (!controller.signal.aborted) setFailed(true) })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [api, path, paperId])

  if (!path || failed) return <span className="text-muted-foreground text-xs">插图无法显示</span>
  return <span className="my-3 flex justify-center">
    {url
      ? <img src={url} alt={alt || "文献插图"} className="max-h-128 max-w-full rounded-sm object-contain" />
      : <span className="bg-muted block h-24 w-full animate-pulse rounded-sm" aria-hidden />}
  </span>
}

/**
 * Split the full text into page-sized chunks so only a window is rendered.
 *
 * Chunks break before headings when the page already has content, and never in
 * the middle of a code fence, table, or display formula.
 */
export function splitMarkdownPages(markdown: string, maxChars = PAGE_CHARS): string[] {
  const lines = markdown.split("\n")
  const atoms: string[] = []
  let buffer: string[] = []
  let fence: string | null = null
  let inMath = false

  const flush = () => {
    if (buffer.length === 0) return
    atoms.push(buffer.join("\n"))
    buffer = []
  }

  for (const line of lines) {
    const trimmed = line.trim()
    const fenceMatch = trimmed.match(/^(```|~~~)/)
    if (fence) {
      buffer.push(line)
      if (fenceMatch) fence = null
      continue
    }
    if (fenceMatch) {
      flush()
      fence = fenceMatch[1]
      buffer.push(line)
      continue
    }
    if (inMath) {
      buffer.push(line)
      if (trimmed.endsWith("$$")) inMath = false
      continue
    }
    if (trimmed.startsWith("$$")) {
      flush()
      inMath = !trimmed.slice(2).includes("$$")
      buffer.push(line)
      continue
    }
    if (trimmed === "") {
      if (buffer.length > 0 && !buffer.at(-1)?.trim()) {
        buffer[buffer.length - 1] = ""
        continue
      }
      buffer.push("")
      continue
    }
    if (/^#{1,6}\s/.test(trimmed)) {
      flush()
      buffer.push(line)
      continue
    }
    if (trimmed.startsWith("|")) {
      buffer.push(line)
      continue
    }
    buffer.push(line)
    if (buffer.join("\n").length >= maxChars) flush()
  }
  flush()

  const pages: string[] = []
  let current = ""
  for (const atom of atoms) {
    const isHeading = /^\s*#{1,6}\s/.test(atom)
    const grows = current.length + atom.length > maxChars
    if (current && (grows || (isHeading && current.length > PAGE_CHARS / 2))) {
      pages.push(current.trim())
      current = ""
    }
    current += (current ? "\n\n" : "") + atom
  }
  if (current.trim()) pages.push(current.trim())
  return pages.length > 0 ? pages : [""]
}

function clampOffset(value: number, max: number): number {
  return Math.max(8, Math.min(value, Math.max(8, max)))
}

/** The parsed full text of one paper, rendered page by page as it scrolls. */
export function PaperMarkdownView({
  paperId,
  title,
  version,
  onBackToPdf,
  onQuote,
}: {
  paperId: string
  title: string | null
  version: string | null
  onBackToPdf: () => void
  onQuote?: (reference: PaperQuote) => boolean
}) {
  const { api } = useApi()
  const markdown = useQuery({
    queryKey: ["paper-markdown", paperId],
    queryFn: () => api.library.markdown(paperId),
  })
  const text = markdown.data?.markdown
  const scroller = useRef<HTMLDivElement | null>(null)
  const article = useRef<HTMLElement | null>(null)
  const [selected, setSelected] = useState<{ text: string; top: number; left: number } | null>(null)

  const pages = useMemo(() => {
    if (text === undefined) return []
    const origin = typeof window === "undefined" ? "" : window.location.origin
    return splitMarkdownPages(linkImages(text, (path) => {
      const url = api.library.assetUrl(paperId, path)
      return /^https?:/.test(url) ? url : `${origin}${url}`
    }))
  }, [api, paperId, text])

  const virtualizer = useVirtualizer({
    count: pages.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => 900,
    overscan: 2,
  })
  const virtualItems = virtualizer.getVirtualItems()

  const components = useMemo(() => ({
    img: (props: { src?: string; alt?: string }) => (
      <MarkdownImage paperId={paperId} source={props.src} alt={props.alt} />
    ),
  }), [paperId])

  function captureSelection() {
    if (!onQuote) return
    const selection = window.getSelection()
    const passage = selection?.toString().trim() ?? ""
    const node = selection?.anchorNode
    const box = scroller.current?.getBoundingClientRect()
    if (!selection || selection.isCollapsed || !passage || !node || !box
      || !article.current?.contains(node)) {
      setSelected(null)
      return
    }
    const rect = selection.getRangeAt(0).getBoundingClientRect()
    setSelected({
      text: passage.slice(0, 2000),
      top: clampOffset(rect.bottom - box.top + 8, box.height - 48),
      left: clampOffset(rect.left - box.left, box.width - 132),
    })
  }

  function addSelection() {
    if (!selected || !onQuote || !version) return
    const accepted = onQuote({
      kind: "markdown_selection",
      user_paper_id: paperId,
      version,
      page: null,
      selected_text: selected.text,
      comment: "",
      source_title: title ?? undefined,
    })
    if (!accepted) notifyError(new Error("无法加入当前对话"), "请检查会话后重试")
    window.getSelection()?.removeAllRanges()
    setSelected(null)
  }

  if (markdown.isError) {
    const unavailable = isApiError(markdown.error)
      && markdown.error.code === "paper_markdown_not_available"
    return <div className="flex min-h-0 flex-1 flex-col items-start gap-3 overflow-y-auto overscroll-contain p-6">
      <p role="alert" className="text-sm text-muted-foreground">
        {unavailable ? "该文献没有 Markdown 全文" : describeError(markdown.error)}
      </p>
      <Button variant="outline" size="sm" onClick={onBackToPdf}>返回 PDF 原文</Button>
    </div>
  }
  if (text === undefined) {
    return <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-6">
      <p className="text-sm text-muted-foreground">加载中…</p>
    </div>
  }

  return <div className="relative min-h-0 flex-1">
    <div
      ref={scroller}
      className="h-full overflow-y-auto overscroll-contain"
      onMouseUp={captureSelection}
      onKeyUp={captureSelection}
    >
      <article
        ref={article}
        className="font-reading relative mx-auto w-full max-w-3xl px-6 py-6"
        style={{ height: virtualizer.getTotalSize() }}
      >
        {virtualItems.map((item) => <div
          key={item.key}
          data-index={item.index}
          ref={virtualizer.measureElement}
          className="absolute inset-x-0 top-0"
          style={{ transform: `translateY(${item.start}px)` }}
        >
          <Markdown components={components}>{pages[item.index] ?? ""}</Markdown>
        </div>)}
      </article>
    </div>
    {selected && <Button
      size="sm"
      className="absolute z-10 shadow-md"
      style={{ top: selected.top, left: selected.left }}
      onMouseDown={(event) => event.preventDefault()}
      onClick={addSelection}
    ><MessageSquarePlus />添加到对话</Button>}
  </div>
}
