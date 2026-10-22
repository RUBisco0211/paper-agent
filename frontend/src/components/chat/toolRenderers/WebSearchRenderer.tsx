import { getResultText } from "@/components/chat/toolRenderers/shared"
import type { ToolCallWithResult, ToolRenderer } from "./types"

interface WebResult {
  title?: string
  url: string
  snippet?: string
}

function readResults(pair: ToolCallWithResult): WebResult[] {
  const text = getResultText(pair.result)
  try {
    const data: unknown = JSON.parse(text)
    if (!data || typeof data !== "object" || !("results" in data)) return []
    const results = (data as { results: unknown }).results
    if (!Array.isArray(results)) return []
    return results.filter(
      (item): item is WebResult =>
        Boolean(item && typeof item === "object" && typeof item.url === "string"),
    )
  } catch {
    return []
  }
}

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
      {results.map((item) => (
        <a
          key={item.url}
          href={item.url}
          target="_blank"
          rel="noreferrer"
          className="block rounded-lg border bg-card p-3 text-sm transition-colors hover:bg-accent"
        >
          <span className="line-clamp-1 font-medium">{item.title || domainOf(item.url)}</span>
          {item.snippet && (
            <span className="mt-1 line-clamp-3 block text-muted-foreground">{item.snippet}</span>
          )}
          <span className="mt-2 block text-xs text-muted-foreground">{domainOf(item.url)}</span>
        </a>
      ))}
    </div>
  )
}

export const WebSearchRenderer: ToolRenderer = {
  renderHeader: () => <span>搜索网页</span>,
  renderBody: (pair) => (pair.result ? <WebResults pair={pair} /> : null),
}
