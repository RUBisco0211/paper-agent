import { AlertTriangle, Bot, Info, Wrench } from "lucide-react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import type { SessionEntry } from "@/lib/api"
import { cn } from "@/lib/utils"

const ERROR_TEXT: Record<string, string> = {
  agent_unavailable: "Agent 执行器尚未接入，本次没有生成回答（会话与队列状态仍然有效）",
  llm_not_configured: "模型配置不完整，请在“模型设置”中补全",
  search_unavailable: "检索服务暂时不可用，本次没有使用论文证据",
  internal_error: "服务内部错误，本次生成已中断",
}

const STOP_TEXT: Record<string, string> = {
  aborted: "已停止：以上是停止前生成的内容",
  failed: "生成失败",
  completed: "",
}

export function EntryList({
  entries,
  streamingText,
  generating,
  onCitationClick,
}: {
  entries: SessionEntry[]
  streamingText: string
  generating: boolean
  onCitationClick: (citationId: string) => void
}) {
  return (
    <div className="flex flex-col gap-4">
      {entries.map((entry) => (
        <EntryItem key={entry.id} entry={entry} onCitationClick={onCitationClick} />
      ))}
      {generating ? (
        <div className="flex gap-3">
          <Avatar role="assistant" />
          <div className="bg-muted/60 min-h-9 flex-1 rounded-lg px-3 py-2 text-sm whitespace-pre-wrap">
            {streamingText || <span className="text-muted-foreground">正在生成…</span>}
            <span className="bg-foreground ml-0.5 inline-block h-4 w-[2px] animate-pulse align-middle" />
          </div>
        </div>
      ) : null}
    </div>
  )
}

function EntryItem({
  entry,
  onCitationClick,
}: {
  entry: SessionEntry
  onCitationClick: (citationId: string) => void
}) {
  const payload = entry.payload as Record<string, unknown>

  if (entry.type === "model_change") {
    return (
      <p className="text-muted-foreground flex items-center gap-1 text-xs">
        <Info className="size-3" />
        模型切换为 {String(payload.provider ?? "?")}/{String(payload.model ?? "?")}
      </p>
    )
  }

  if (entry.type === "tool_result") {
    return (
      <details className="bg-muted/40 rounded-md border px-3 py-2 text-sm">
        <summary className="flex cursor-pointer items-center gap-2">
          <Wrench className="size-3.5" />
          工具：{String(payload.tool ?? "tool")}
          {payload.status ? <Badge variant="muted">{String(payload.status)}</Badge> : null}
        </summary>
        <pre className="text-muted-foreground mt-2 max-h-64 overflow-auto text-xs whitespace-pre-wrap">
          {String(payload.content ?? "")}
        </pre>
      </details>
    )
  }

  const role = String(payload.role ?? "assistant")
  const content = String(payload.content ?? "")
  const stopReason = payload.stop_reason ? String(payload.stop_reason) : null
  const errorCode = payload.error_code ? String(payload.error_code) : null
  const citations = Array.isArray(payload.citations) ? (payload.citations as unknown[]) : []

  if (role === "user") {
    return (
      <div className="flex justify-end gap-3">
        <div className="bg-primary text-primary-foreground max-w-[80%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap">
          {content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-3">
      <Avatar role={role} />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        {content ? (
          <div className="bg-muted/60 rounded-lg px-3 py-2 text-sm whitespace-pre-wrap">
            {content}
          </div>
        ) : null}
        {stopReason && STOP_TEXT[stopReason] ? (
          <p
            className={cn(
              "text-xs",
              stopReason === "failed" ? "text-destructive" : "text-muted-foreground",
            )}
          >
            {STOP_TEXT[stopReason]}
          </p>
        ) : null}
        {errorCode ? (
          <Alert variant="warning">
            <AlertTriangle />
            <AlertDescription>{ERROR_TEXT[errorCode] ?? errorCode}</AlertDescription>
          </Alert>
        ) : null}
        {citations.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {citations.map((citation) => (
              <button
                key={String(citation)}
                type="button"
                onClick={() => onCitationClick(String(citation))}
                className="focus-visible:ring-ring rounded-md focus-visible:ring-2 focus-visible:outline-none"
              >
                <Badge variant="outline" className="hover:bg-accent cursor-pointer">
                  [{String(citation)}]
                </Badge>
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}

function Avatar({ role }: { role: string }) {
  if (role === "user") {
    return null
  }
  return (
    <span className="bg-secondary text-secondary-foreground mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full">
      <Bot className="size-4" />
    </span>
  )
}
