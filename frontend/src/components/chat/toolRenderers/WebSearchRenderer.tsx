import { getResultText } from "@/components/chat/toolRenderers/shared"
import { readFailureCode } from "./webFailure"
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
  const failure = readFailureCode(getResultText(pair.result))
  if (pair.result?.state === "error" || failure) {
    return (
      <p role="alert" className="p-3 font-mono text-sm text-destructive">
        {failure ?? "provider_unavailable"}
      </p>
    )
  }
  const results = readResults(pair)
  if (!results.length) {
    return <p className="p-3 text-sm text-muted-foreground">no results</p>
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
  renderHeader: () => <span>web search</span>,
  renderBody: (pair) => (pair.result ? <WebResults pair={pair} /> : null),
}
