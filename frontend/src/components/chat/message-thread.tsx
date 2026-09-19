import { Brain, Bot, ChevronDown, FileSearch, Library, Search, Wrench } from "lucide-react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Bubble, BubbleContent } from "@/components/ui/bubble"
import { Button } from "@/components/ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import {
  Message,
  MessageContent,
  MessageGroup,
  MessageHeader,
} from "@/components/ui/message"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller"
import { Spinner } from "@/components/ui/spinner"
import type { SessionEntry } from "@/lib/api"

import { inlineCitationIds, MarkdownContent } from "./markdown-content"

export interface ActiveTool {
  id: string
  name: string
}

const ERROR_TEXT: Record<string, string> = {
  agent_unavailable: "暂时无法生成回答，请稍后重试",
  agent_timeout: "回答超时，请缩小问题范围后重试",
  agent_max_iters: "检索步骤过多，本次回答未能完成",
  llm_not_configured: "问答服务暂时不可用",
  provider_rate_limited: "问答服务繁忙，请稍后重试",
  provider_unavailable: "问答服务暂时不可用，请稍后重试",
  search_unavailable: "检索暂时不可用，本次回答没有使用文献内容",
  internal_error: "生成中断，请重试",
}

const TOOL_LABEL: Record<string, string> = {
  list_papers: "查看文献范围",
  search_papers: "检索文献",
  get_paper_excerpt: "读取引用原文",
}

const TOOL_ICON: Record<string, typeof Wrench> = {
  list_papers: Library,
  search_papers: Search,
  get_paper_excerpt: FileSearch,
}

export function MessageThread({
  entries,
  streamingText,
  streamingThinking = "",
  generating,
  activeTools = [],
  onCitationClick,
}: {
  entries: SessionEntry[]
  streamingText: string
  streamingThinking?: string
  generating: boolean
  activeTools?: ActiveTool[]
  onCitationClick: (citationId: string) => void
}) {
  const visibleEntries = entries.filter((entry) => entry.type !== "session_context")
  const timeline = buildTimeline(visibleEntries)
  const showingStream = generating || Boolean(streamingText) || Boolean(streamingThinking)

  return (
    <MessageScrollerProvider autoScroll>
      <MessageScroller className="h-full">
        <MessageScrollerViewport>
          <MessageScrollerContent className="mx-auto w-full max-w-3xl p-4 md:p-6">
            {visibleEntries.length === 0 && !showingStream ? <ConversationEmpty /> : null}
            {timeline.map((item) => (
              <MessageScrollerItem
                key={item.id}
                messageId={item.id}
                scrollAnchor={item.kind === "entry" && item.entry.payload.role === "user"}
              >
                {item.kind === "turn" ? (
                  <AssistantTurn
                    answer={item.answer}
                    trace={item.trace}
                    elapsedMs={item.elapsedMs}
                    onCitationClick={onCitationClick}
                  />
                ) : (
                  <EntryRow entry={item.entry} onCitationClick={onCitationClick} />
                )}
              </MessageScrollerItem>
            ))}
            {showingStream ? (
              <MessageScrollerItem messageId="streaming" scrollAnchor>
                <AssistantMessage
                  content={streamingText}
                  thinking={streamingThinking}
                  loading={generating}
                  activeTools={activeTools}
                />
              </MessageScrollerItem>
            ) : null}
          </MessageScrollerContent>
        </MessageScrollerViewport>
        <MessageScrollerButton />
      </MessageScroller>
    </MessageScrollerProvider>
  )
}

type TimelineItem =
  | { kind: "entry"; id: string; entry: SessionEntry }
  | {
      kind: "turn"
      id: string
      answer: SessionEntry
      trace: SessionEntry[]
      elapsedMs: number
    }

function buildTimeline(entries: SessionEntry[]): TimelineItem[] {
  const timeline: TimelineItem[] = []
  let trace: SessionEntry[] = []
  let turnStartedAt: number | null = null

  for (const entry of entries) {
    const role = String(entry.payload.role ?? "")
    const isTraceMessage = entry.type === "message" && role === "assistant" && entry.payload.trace

    if (role === "user") {
      timeline.push(...trace.map((item) => ({ kind: "entry" as const, id: item.id, entry: item })))
      trace = []
      turnStartedAt = Date.parse(entry.timestamp)
      timeline.push({ kind: "entry", id: entry.id, entry })
    } else if (entry.type === "tool_result" || isTraceMessage) {
      trace.push(entry)
    } else if (entry.type === "message" && role === "assistant") {
      timeline.push({
        kind: "turn",
        id: entry.id,
        answer: entry,
        trace,
        elapsedMs: Math.max(0, Date.parse(entry.timestamp) - (turnStartedAt ?? Date.parse(entry.timestamp))),
      })
      trace = []
      turnStartedAt = null
    } else {
      timeline.push(...trace.map((item) => ({ kind: "entry" as const, id: item.id, entry: item })))
      trace = []
      timeline.push({ kind: "entry", id: entry.id, entry })
    }
  }

  timeline.push(...trace.map((item) => ({ kind: "entry" as const, id: item.id, entry: item })))
  return timeline
}

function AssistantTurn({
  answer,
  trace,
  elapsedMs,
  onCitationClick,
}: {
  answer: SessionEntry
  trace: SessionEntry[]
  elapsedMs: number
  onCitationClick: (citationId: string) => void
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      {trace.length > 0 ? <TraceBlock entries={trace} elapsedMs={elapsedMs} /> : null}
      <EntryRow entry={answer} onCitationClick={onCitationClick} />
    </div>
  )
}

function TraceBlock({ entries, elapsedMs }: { entries: SessionEntry[]; elapsedMs: number }) {
  return (
    <Collapsible className="w-full">
      <CollapsibleTrigger asChild>
        <Marker asChild className="group h-6 min-h-0 w-full cursor-pointer gap-1.5 font-medium">
          <button type="button">
            <MarkerContent className="flex-none">用时 {formatElapsed(elapsedMs)}</MarkerContent>
            <ChevronDown className="transition-transform group-data-[state=open]:rotate-180" />
          </button>
        </Marker>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="flex w-full flex-col gap-0.5 pt-0.5">
          {entries.map((entry) =>
            entry.type === "tool_result" ? (
              <ToolResult key={entry.id} payload={entry.payload as Record<string, unknown>} />
            ) : (
              <div key={entry.id} className="w-full py-0.5 text-muted-foreground">
                <MarkdownContent className="text-sm leading-6">
                  {String(entry.payload.content ?? "")}
                </MarkdownContent>
              </div>
            ),
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function formatElapsed(milliseconds: number) {
  const seconds = Math.max(1, Math.round(milliseconds / 1000))
  if (seconds < 60) return `${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  return `${minutes} 分 ${seconds % 60} 秒`
}

function ConversationEmpty() {
  return (
    <Empty className="border-0">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Bot />
        </EmptyMedia>
        <EmptyTitle>从文献开始提问</EmptyTitle>
        <EmptyDescription>可以询问结论、方法、实验结果，或比较多篇文献。</EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}

function EntryRow({
  entry,
  onCitationClick,
}: {
  entry: SessionEntry
  onCitationClick: (citationId: string) => void
}) {
  const payload = entry.payload as Record<string, unknown>

  if (entry.type === "model_change") {
    return (
      <Marker variant="separator">
        <MarkerIcon>
          <Bot />
        </MarkerIcon>
        <MarkerContent>开始新的回答</MarkerContent>
      </Marker>
    )
  }

  if (entry.type === "tool_result") {
    return <ToolResult payload={payload} />
  }

  const role = String(payload.role ?? "assistant")
  const content = String(payload.content ?? "")
  const stopReason = payload.stop_reason ? String(payload.stop_reason) : null
  const errorCode = payload.error_code ? String(payload.error_code) : null
  const citations = Array.isArray(payload.citations) ? payload.citations : []
  const thinking = String(payload.thinking ?? "")

  if (role === "user") {
    return (
      <Message align="end">
        <MessageContent>
          <Bubble variant="default" align="end">
            <BubbleContent className="whitespace-pre-wrap">{content}</BubbleContent>
          </Bubble>
        </MessageContent>
      </Message>
    )
  }

  return (
    <AssistantMessage
      content={content}
      thinking={thinking}
      stopReason={stopReason}
      errorCode={errorCode}
      citations={citations.map(String)}
      onCitationClick={onCitationClick}
    />
  )
}

function AssistantMessage({
  content,
  thinking = "",
  stopReason,
  errorCode,
  citations = [],
  loading = false,
  activeTools = [],
  onCitationClick,
}: {
  content: string
  thinking?: string
  stopReason?: string | null
  errorCode?: string | null
  citations?: string[]
  loading?: boolean
  activeTools?: ActiveTool[]
  onCitationClick?: (citationId: string) => void
}) {
  const inlineCitations = inlineCitationIds(content, citations)
  const remainingCitations = citations.filter((citation) => !inlineCitations.has(citation))

  return (
    <MessageGroup>
      <Message align="start">
        <MessageContent>
          <MessageHeader>Paper Agent</MessageHeader>

          {thinking ? <ThinkingBlock content={thinking} streaming={loading} /> : null}

          {activeTools.length > 0 ? (
            <div className="flex flex-col gap-1">
              {activeTools.map((tool) => (
                <LiveTool key={tool.id} name={tool.name} />
              ))}
            </div>
          ) : null}

          {content ? (
            <Bubble variant="ghost" align="start">
              <BubbleContent className="min-w-0">
                <MarkdownContent
                  streaming={loading}
                  citations={citations}
                  onCitationClick={onCitationClick}
                >
                  {content}
                </MarkdownContent>
              </BubbleContent>
            </Bubble>
          ) : null}

          {loading && !content && !thinking && activeTools.length === 0 ? (
            <Marker>
              <MarkerIcon>
                <Spinner />
              </MarkerIcon>
              <MarkerContent className="shimmer">正在思考…</MarkerContent>
            </Marker>
          ) : null}

          {loading && content ? (
            <Marker>
              <MarkerIcon>
                <Spinner />
              </MarkerIcon>
              <MarkerContent className="shimmer">正在生成…</MarkerContent>
            </Marker>
          ) : null}

          {stopReason === "aborted" ? <Badge variant="outline">已停止</Badge> : null}

          {errorCode ? (
            <Alert variant="destructive">
              <AlertDescription>
                {ERROR_TEXT[errorCode] ?? "生成失败，请重试"}
              </AlertDescription>
            </Alert>
          ) : null}

          {remainingCitations.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {remainingCitations.map((citation) => (
                <Button
                  key={citation}
                  variant="outline"
                  size="sm"
                  onClick={() => onCitationClick?.(citation)}
                >
                  <FileSearch data-icon="inline-start" />
                  引用 {citations.indexOf(citation) + 1}
                </Button>
              ))}
            </div>
          ) : null}
        </MessageContent>
      </Message>
    </MessageGroup>
  )
}

function ThinkingBlock({ content, streaming }: { content: string; streaming: boolean }) {
  return (
    <Collapsible defaultOpen={streaming} className="rounded-lg border bg-muted/40">
      <CollapsibleTrigger asChild>
        <Button variant="ghost" size="sm" className="w-full justify-start px-3">
          {streaming ? <Spinner data-icon="inline-start" /> : <Brain data-icon="inline-start" />}
          {streaming ? "正在思考…" : "思考过程"}
          <ChevronDown data-icon="inline-end" className="ml-auto" />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="text-muted-foreground mx-3 mb-3 border-l pl-3">
          <MarkdownContent streaming={streaming}>{content}</MarkdownContent>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function LiveTool({ name }: { name: string }) {
  const Icon = TOOL_ICON[name] ?? Wrench
  return (
    <Marker>
      <MarkerIcon>
        <Spinner />
      </MarkerIcon>
      <MarkerContent className="flex items-center gap-2">
        <Icon />
        {TOOL_LABEL[name] ?? "正在使用工具"}
      </MarkerContent>
    </Marker>
  )
}

function ToolResult({ payload }: { payload: Record<string, unknown> }) {
  const name = String(payload.tool ?? "tool")
  const state = String(payload.state ?? "")
  const content = formatToolContent(payload.content)
  const Icon = TOOL_ICON[name] ?? Wrench

  return (
    <Collapsible className="w-full">
      {content.value ? (
        <CollapsibleTrigger asChild>
          <Marker
            asChild
            className="group h-6 min-h-0 w-full cursor-pointer gap-1.5 font-medium"
          >
            <button type="button">
              <MarkerIcon>
                <Icon />
              </MarkerIcon>
              <MarkerContent className="flex-none">
                {TOOL_LABEL[name] ?? "工具调用"}
              </MarkerContent>
              {state && state !== "success" ? (
                <Badge variant="destructive">未完成</Badge>
              ) : null}
              <ChevronDown className="transition-transform group-data-[state=open]:rotate-180" />
            </button>
          </Marker>
        </CollapsibleTrigger>
      ) : (
        <Marker className="h-6 min-h-0 w-full gap-1.5 font-medium">
          <MarkerIcon>
            <Icon />
          </MarkerIcon>
          <MarkerContent>{TOOL_LABEL[name] ?? "工具调用"}</MarkerContent>
        </Marker>
      )}
      {content.value ? (
        <CollapsibleContent className="w-full">
          <div className="w-full overflow-x-auto py-1">
            {content.isJson ? (
              <MarkdownContent className="text-xs leading-5">
                {fencedCode(content.value, "json")}
              </MarkdownContent>
            ) : (
              <pre className="text-xs whitespace-pre-wrap">{content.value}</pre>
            )}
          </div>
        </CollapsibleContent>
      ) : null}
    </Collapsible>
  )
}

function formatToolContent(content: unknown): { value: string; isJson: boolean } {
  if (content === null || content === undefined || content === "") {
    return { value: "", isJson: false }
  }

  if (typeof content !== "string") {
    return { value: JSON.stringify(content, null, 2), isJson: true }
  }

  try {
    return { value: JSON.stringify(JSON.parse(content), null, 2), isJson: true }
  } catch {
    const trimmed = content.trimStart()
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      return { value: formatIncompleteJson(content), isJson: true }
    }
    return { value: content, isJson: false }
  }
}

function formatIncompleteJson(content: string): string {
  let result = ""
  let indent = 0
  let inString = false
  let escaped = false

  const newline = () => {
    result = result.trimEnd() + "\n" + "  ".repeat(indent)
  }

  for (const character of content) {
    if (inString) {
      result += character
      if (escaped) escaped = false
      else if (character === "\\") escaped = true
      else if (character === '"') inString = false
      continue
    }

    if (character === '"') {
      inString = true
      result += character
    } else if (character === "{" || character === "[") {
      result += character
      indent += 1
      newline()
    } else if (character === "}" || character === "]") {
      indent = Math.max(0, indent - 1)
      newline()
      result += character
    } else if (character === ",") {
      result += character
      newline()
    } else if (character === ":") {
      result += ": "
    } else if (!/\s/.test(character)) {
      result += character
    }
  }

  return result.trim()
}

function fencedCode(content: string, language: string): string {
  const longestRun = Math.max(0, ...Array.from(content.matchAll(/`+/g), (match) => match[0].length))
  const fence = "`".repeat(Math.max(3, longestRun + 1))
  return `${fence}${language}\n${content}\n${fence}`
}
