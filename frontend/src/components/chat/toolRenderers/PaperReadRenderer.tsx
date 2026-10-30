import { FileImage, FileText, LocateFixed } from "lucide-react"
import { useState } from "react"

import { usePaperOpen } from "@/components/chat/CitationProvider"
import { Markdown } from "@/components/markdown/Markdown"
import { Button } from "@/components/ui/Button"
import {
  ImageViewerDialog,
  type ImageViewerTarget,
} from "@/components/papers/ImageViewerDialog"
import {
  getResultText,
  toolArgClass,
  toolLabelClass,
} from "@/components/chat/toolRenderers/shared"
import type { ToolCallWithResult, ToolRenderer } from "./types"
import type { DataBlock, ToolResultBlock } from "@agentscope-ai/agentscope/message"

interface PageMeta {
  title?: string | null
  page?: number
  total_pages?: number
  markdown?: string
  images?: { block_id: number; caption?: string | null }[]
  truncated?: boolean
}

interface ImageMeta {
  title?: string | null
  page?: number
  caption?: string | null
  note?: string
}

/** The tool result carries base64 data, not a URL, so it becomes a data URI. */
function imageSource(result?: ToolResultBlock): { source: string; mediaType: string } | null {
  if (!result || typeof result.output === "string") return null
  for (const block of result.output) {
    if (block.type !== "data") continue
    const source = (block as DataBlock).source
    if (source.type === "base64") {
      return {
        source: `data:${source.media_type};base64,${source.data}`,
        mediaType: source.media_type,
      }
    }
    return { source: String(source.url), mediaType: source.media_type }
  }
  return null
}

function readMeta<T>(result?: ToolResultBlock): T | null {
  if (!result || result.state === "error" || result.state === "running") return null
  try {
    const data: unknown = JSON.parse(getResultText(result))
    return data && typeof data === "object" ? (data as T) : null
  } catch {
    return null
  }
}

function pageArg(pair: ToolCallWithResult): number | null {
  try {
    const input: unknown = JSON.parse(pair.call.input || "{}")
    if (input && typeof input === "object" && "page" in input) {
      const page = (input as { page?: unknown }).page
      if (typeof page === "number" && Number.isFinite(page)) return page
    }
  } catch {
    return null
  }
  return null
}

/** The call arguments carry the locator the image result itself does not. */
function imageArgs(pair: ToolCallWithResult): { paperId: string | null; blockId: number | null } {
  try {
    const input: unknown = JSON.parse(pair.call.input || "{}")
    if (input && typeof input === "object") {
      const { paper_id, block_id } = input as { paper_id?: unknown; block_id?: unknown }
      return {
        paperId: typeof paper_id === "string" && paper_id ? paper_id : null,
        blockId: typeof block_id === "number" && Number.isInteger(block_id) ? block_id : null,
      }
    }
  } catch {
    // The model wrote these arguments; a malformed call simply has no locator.
  }
  return { paperId: null, blockId: null }
}

/**
 * Jumps to the figure in the conversation's reader.
 *
 * The result carries only title, page and caption, so the paper and block ids
 * come from the call arguments; outside a conversation there is nowhere to go
 * and the button is omitted.
 */
function LocateButton({ paperId, page, blockId }: { paperId: string | null; page?: number; blockId: number | null }) {
  const openPaper = usePaperOpen()
  if (!openPaper || !paperId) return null
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="gap-1"
      onClick={() => openPaper({ kind: "parsed_block", user_paper_id: paperId, page: page ?? null, block_id: blockId ?? undefined })}
    >
      <LocateFixed />
      定位原文
    </Button>
  )
}

function PendingBody() {
  return <p className="p-3 text-sm text-muted-foreground">正在读取文献内容…</p>
}

function FailedBody() {
  return <p role="alert" className="p-3 text-sm text-destructive">读取失败，请重试</p>
}

/**
 * One page of parsed full text. The page is rendered as Markdown because it
 * carries formulas and tables; the raw tool payload never reaches the screen.
 */
export const PaperPageRenderer: ToolRenderer = {
  renderHeader(pair) {
    const page = pageArg(pair)
    return (
      <>
        <FileText className="size-3.5 shrink-0 text-muted-foreground" />
        <span className={toolLabelClass}>读取正文</span>
        {page !== null && <span className={toolArgClass}>第 {page} 页</span>}
      </>
    )
  },
  renderBody(pair) {
    if (!pair.result) return null
    if (pair.result.state === "running") return <PendingBody />
    if (pair.result.state === "error") return <FailedBody />
    const meta = readMeta<PageMeta>(pair.result)
    if (!meta || typeof meta.markdown !== "string" || !meta.markdown.trim()) {
      return <p className="p-3 text-sm text-muted-foreground">这一页没有可读取的正文</p>
    }
    const images = meta.images ?? []
    return (
      <div className="space-y-2 p-3">
        <Markdown className="text-sm">{meta.markdown}</Markdown>
        {images.length > 0 && (
          <p className="text-xs text-muted-foreground">
            本页图片：{images.map((item) => `第 ${item.block_id} 块`).join("、")}
          </p>
        )}
        {meta.truncated && (
          <p className="text-xs text-muted-foreground">本页内容超出单次读取上限，其余部分未返回</p>
        )}
      </div>
    )
  },
}

/**
 * One figure. The picture arrives as a data block; a text-only model never
 * receives it, so the caption and page stand in for the image.
 */
export const PaperImageRenderer: ToolRenderer = {
  renderHeader(pair) {
    const meta = readMeta<ImageMeta>(pair.result)
    return (
      <>
        <FileImage className="size-3.5 shrink-0 text-muted-foreground" />
        <span className={toolLabelClass}>读取图片</span>
        {meta?.page ? <span className={toolArgClass}>第 {meta.page} 页</span> : null}
      </>
    )
  },
  renderBody(pair) {
    if (!pair.result) return null
    if (pair.result.state === "running") return <PendingBody />
    if (pair.result.state === "error") return <FailedBody />
    const meta = readMeta<ImageMeta>(pair.result)
    const src = imageSource(pair.result)
    const { paperId, blockId } = imageArgs(pair)
    if (!src) {
      return (
        <div className="space-y-2 p-3">
          <p className="text-sm text-muted-foreground">
            {meta?.note || "当前模型没有收到图片，只能提供图注与页码"}
            {meta?.caption ? `：${meta.caption}` : ""}
          </p>
          <LocateButton paperId={paperId} page={meta?.page} blockId={blockId} />
        </div>
      )
    }
    const caption = meta?.caption?.trim()
    return (
      <FigureBody
        source={src.source}
        filename={`${caption || "figure"}.${src.mediaType.split("/")[1]?.replace("jpeg", "jpg") || "png"}`}
        caption={caption}
        page={meta?.page}
        paperId={paperId}
        blockId={blockId}
      />
    )
  },
}

/**
 * The thumbnail opens the shared large-image viewer, so a figure found in a
 * tool result zooms the same way as one on the reading page.
 */
function FigureBody({
  source,
  filename,
  caption,
  page,
  paperId,
  blockId,
}: {
  source: string
  filename: string
  caption?: string
  page?: number
  paperId: string | null
  blockId: number | null
}) {
  const [viewer, setViewer] = useState<ImageViewerTarget | null>(null)
  const title = caption || "文献图片"
  return (
    <figure className="space-y-2 p-3">
      <button
        type="button"
        aria-label={`查看大图：${title}`}
        className="block max-w-full cursor-zoom-in rounded border bg-white"
        onClick={() => setViewer({ source, title, filename })}
      >
        <img
          src={source}
          alt={title}
          loading="lazy"
          className="max-h-80 w-auto max-w-full rounded"
        />
      </button>
      <figcaption className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>{[caption, page ? `第 ${page} 页` : null].filter(Boolean).join(" · ")}</span>
        <LocateButton paperId={paperId} page={page} blockId={blockId} />
      </figcaption>
      <ImageViewerDialog target={viewer} onOpenChange={setViewer} />
    </figure>
  )
}
