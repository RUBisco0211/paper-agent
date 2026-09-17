import { Bot, Wrench } from "lucide-react"
import { Fragment } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Bubble, BubbleContent } from "@/components/ui/bubble"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import {
  Message,
  MessageAvatar,
  MessageContent,
  MessageGroup,
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
import { cn } from "cn"

const ERROR_TEXT: Record<string, string> = {
  agent_unavailable: "暂时无法生成回答，请稍后重试",
  llm_not_configured: "模型配置不完整，请到模型设置中补齐",
  search_unavailable: "检索暂时不可用，本次回答没有使用文献内容",
  internal_error: "生成中断，请重试",
}

const STOP_TEXT: Record<string, string> = {
  aborted: "已停止",
  failed: "",
  completed: "",
}

/**
 * One conversation thread.
 *
 * Scroll following, anchoring and jump-to-latest belong to `MessageScroller`;
 * rows use `Message`, surfaces use `Bubble`, and non-message notes use `Marker`.
 */
export function MessageThread({
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
    <MessageScrollerProvider autoScroll>
      <MessageScroller className="h-full">
        <MessageScrollerViewport>
          <MessageScrollerContent className="mx-auto w-full max-w-3xl p-4">
            {entries.map((entry) => (
              <MessageScrollerItem
                key={entry.id}
                messageId={entry.id}
                scrollAnchor={entry.payload.role === "user"}
              >
                <EntryRow entry={entry} onCitationClick={onCitationClick} />
              </MessageScrollerItem>
            ))}
            {generating ? (
              <MessageScrollerItem messageId="streaming" scrollAnchor>
                <Message align="start">
                  <MessageAvatar>
                    <Avatar>
                      <AvatarFallback>
                        <Bot />
                      </AvatarFallback>
                    </Avatar>
                  </MessageAvatar>
                  <MessageContent>
                    <Bubble variant="secondary" align="start">
                      <BubbleContent
                        className={cn(!streamingText && "flex items-center gap-2")}
                      >
                        {streamingText || (
                          <>
                            <Spinner data-icon="inline-start" />
                            <span className="shimmer">正在生成…</span>
                          </>
                        )}
                      </BubbleContent>
                    </Bubble>
                  </MessageContent>
                </Message>
              </MessageScrollerItem>
            ) : null}
          </MessageScrollerContent>
        </MessageScrollerViewport>
        <MessageScrollerButton />
      </MessageScroller>
    </MessageScrollerProvider>
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
      <Marker variant="border">
        <MarkerIcon>
          <Bot />
        </MarkerIcon>
        <MarkerContent>
          模型：{String(payload.provider ?? "?")} / {String(payload.model ?? "?")}
        </MarkerContent>
      </Marker>
    )
  }

  if (entry.type === "tool_result") {
    return (
      <Message align="start">
        <MessageAvatar>
          <Avatar>
            <AvatarFallback>
              <Wrench />
            </AvatarFallback>
          </Avatar>
        </MessageAvatar>
        <MessageContent>
          <Bubble variant="outline" align="start">
            <BubbleContent>
              <Collapsible>
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" size="sm">
                    <Wrench data-icon="inline-start" />
                    {String(payload.tool ?? "工具")}
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <pre className="text-muted-foreground max-h-64 overflow-auto text-xs whitespace-pre-wrap">
                    {String(payload.content ?? "")}
                  </pre>
                </CollapsibleContent>
              </Collapsible>
            </BubbleContent>
          </Bubble>
        </MessageContent>
      </Message>
    )
  }

  const role = String(payload.role ?? "assistant")
  const content = String(payload.content ?? "")
  const stopReason = payload.stop_reason ? String(payload.stop_reason) : null
  const errorCode = payload.error_code ? String(payload.error_code) : null
  const citations = Array.isArray(payload.citations) ? payload.citations : []

  if (role === "user") {
    return (
      <Message align="end">
        <MessageContent>
          <Bubble variant="default" align="end">
            <BubbleContent>{content}</BubbleContent>
          </Bubble>
        </MessageContent>
      </Message>
    )
  }

  return (
    <MessageGroup>
      <Message align="start">
        <MessageAvatar>
          <Avatar>
            <AvatarFallback>
              <Bot />
            </AvatarFallback>
          </Avatar>
        </MessageAvatar>
        <MessageContent>
          {content ? (
            <Bubble variant="secondary" align="start">
              <BubbleContent>{content}</BubbleContent>
            </Bubble>
          ) : null}

          {stopReason && STOP_TEXT[stopReason] ? (
            <Badge variant="outline">{STOP_TEXT[stopReason]}</Badge>
          ) : null}

          {errorCode ? (
            <Alert>
              <AlertDescription>
                {ERROR_TEXT[errorCode] ?? "生成失败，请重试"}
              </AlertDescription>
            </Alert>
          ) : null}

          {citations.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {citations.map((citation) => (
                <Fragment key={String(citation)}>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onCitationClick(String(citation))}
                  >
                    {String(citation)}
                  </Button>
                </Fragment>
              ))}
            </div>
          ) : null}
        </MessageContent>
      </Message>
    </MessageGroup>
  )
}
