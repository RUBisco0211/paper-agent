import { getResultText, parseInput } from "@/components/chat/toolRenderers/shared"
import { WebToolError, isFailure } from "./WebToolResult"
import type { ToolCallWithResult, ToolRenderer } from "./types"

interface PageRead {
  content: string
  url: string
  excerptOnly: boolean
  outOfRange: boolean
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

/**
 * Read a page result, or the failure the agent tools report in the same shape.
 * A failure has no `url`, so the caller can tell them apart.
 */
function readPage(pair: ToolCallWithResult): PageRead | null {
  const text = getResultText(pair.result)
  try {
    const data: unknown = JSON.parse(text)
    if (!data || typeof data !== "object") return null
    const payload = data as {
      status?: unknown
      content?: unknown
      url?: unknown
      excerpt_only?: unknown
      offset_out_of_range?: unknown
    }
    if (typeof payload.content !== "string") return null
    return {
      content: payload.content,
      url: typeof payload.url === "string" ? payload.url : "",
      excerptOnly: payload.excerpt_only === true,
      outOfRange: payload.offset_out_of_range === true,
    }
  } catch {
    return null
  }
}

function PageReadView({ pair }: { pair: ToolCallWithResult }) {
  if (pair.result?.state === "error" || isFailure(getResultText(pair.result))) {
    return <WebToolError />
  }
  const page = readPage(pair)
  if (!page) {
    return <p className="p-3 text-sm text-muted-foreground">无内容</p>
  }
  return (
    <div className="space-y-2 p-3 text-sm">
      <a
        href={page.url}
        target="_blank"
        rel="noreferrer"
        className="block truncate font-medium underline"
      >
        {domainOf(page.url)}
      </a>
      {page.excerptOnly && (
        <p className="text-xs text-muted-foreground">以下是与问题相关的摘录</p>
      )}
      {page.outOfRange ? (
        <p className="text-muted-foreground">已读到页面末尾</p>
      ) : (
        <pre className="max-h-80 overflow-y-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 font-sans text-xs">
          {page.content}
        </pre>
      )}
    </div>
  )
}

function headerFor(label: string) {
  return (pair: ToolCallWithResult) => {
    const input = parseInput(pair.call.input) as { url?: unknown }
    const url = typeof input.url === "string" ? input.url : ""
    return (
      <span className="truncate">
        {label} {url ? domainOf(url) : ""}
      </span>
    )
  }
}

export const WebFetchRenderer: ToolRenderer = {
  renderHeader: headerFor("读取网页"),
  renderBody: (pair) => (pair.result ? <PageReadView pair={pair} /> : null),
}

export const WebExcerptRenderer: ToolRenderer = {
  renderHeader: headerFor("摘录网页"),
  renderBody: (pair) => (pair.result ? <PageReadView pair={pair} /> : null),
}
