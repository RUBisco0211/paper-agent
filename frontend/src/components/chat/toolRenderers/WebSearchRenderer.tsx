import { getResultText } from "@/components/chat/toolRenderers/shared"
import type { ToolCallWithResult, ToolRenderer } from "./types"

interface WebResult {
  title?: string
  url: string
  snippet?: string
}

const SNIPPET_LIMIT = 200

function readResults(pair: ToolCallWithResult): WebResult[] {
  const text = getResultText(pair.result)
  try {
    const data: unknown = JSON.parse(text)
    if (!data || typeof data !== "object") return []
    const results = (data as { results?: unknown }).results
    if (!Array.isArray(results)) return []
    return results.filter(
      (item): item is WebResult =>
        Boolean(item && typeof item === "object" && typeof item.url === "string"),
    )
  } catch {
    return []
  }
}

/**
 * Read a failure the agent tools report as an ordinary result. The business
 * service's HTTP errors reach the agent already translated into this shape.
 */
function readFailure(pair: ToolCallWithResult): string | null {
  const text = getResultText(pair.result)
  try {
    const data: unknown = JSON.parse(text)
    if (!data || typeof data !== "object") return null
    const { status, message } = data as { status?: unknown; message?: unknown }
    if (status === "error" && typeof message === "string") return message
    return null
  } catch {
    return null
  }
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

function shorten(text: string): string {
  return text.length > SNIPPET_LIMIT ? `${text.slice(0, SNIPPET_LIMIT)}…` : text
}

function WebResults({ pair }: { pair: ToolCallWithResult }) {
  const failure = readFailure(pair)
  if (pair.result?.state === "error" || failure) {
    return (
      <p role="alert" className="p-3 text-sm text-destructive">
        {failure ?? "联网搜索暂不可用，请重试"}
      </p>
    )
  }
  const results = readResults(pair)
  if (!results.length) {
    return <p className="p-3 text-sm text-muted-foreground">没有找到相关网页</p>
  }
  return (
    <div className="space-y-2 py-2">
      {results.map((item, index) => (
        <a
          key={`${item.url}-${index}`}
          href={item.url}
          target="_blank"
          rel="noreferrer"
          className="block rounded-lg border bg-background p-3 text-sm transition-colors hover:bg-accent"
        >
          <span className="line-clamp-1 font-medium break-words">
            {item.title || domainOf(item.url)}
          </span>
          {item.snippet && (
            <span className="mt-1 line-clamp-3 block break-words text-muted-foreground">
              {shorten(item.snippet)}
            </span>
          )}
          <span className="mt-2 block text-xs break-words text-muted-foreground">
            {domainOf(item.url)}
          </span>
        </a>
      ))}
    </div>
  )
}

export const WebSearchRenderer: ToolRenderer = {
  renderHeader: () => <span>搜索网页</span>,
  renderBody: (pair) => (pair.result ? <WebResults pair={pair} /> : null),
}
