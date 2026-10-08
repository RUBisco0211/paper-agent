import { getTextContent, type Msg } from "@agentscope-ai/agentscope/message"
import { useEffect, useRef, useState } from "react"

import { useMessageScroller, useMessageScrollerVisibility } from "@upstream/components/ui/message-scroller"

function messagePreview(message: Msg): string {
  const text = getTextContent(message)?.replace(/\s+/g, " ").trim()
  if (!text) return "暂无文字内容"
  return text.length > 140 ? `${text.slice(0, 140)}…` : text
}

export function MessageNavigationRail({ messages }: { messages: Msg[] }) {
  const { scrollToMessage } = useMessageScroller()
  const { currentAnchorId, visibleMessageIds } = useMessageScrollerVisibility()
  const [open, setOpen] = useState(false)
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [scrollTargetId, setScrollTargetId] = useState<string | null>(null)
  const railRef = useRef<HTMLElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const activeRef = useRef<HTMLButtonElement>(null)
  const activeId = currentAnchorId ?? visibleMessageIds[0] ?? messages.at(-1)?.id

  useEffect(() => {
    const rail = railRef.current
    const active = activeRef.current
    if (!rail || !active) return
    const top = active.getBoundingClientRect().top - rail.getBoundingClientRect().top + rail.scrollTop
    if (top < rail.scrollTop) rail.scrollTop = top
    else if (top + active.offsetHeight > rail.scrollTop + rail.clientHeight) {
      rail.scrollTop = top + active.offsetHeight - rail.clientHeight
    }
  }, [activeId, messages.length])

  useEffect(() => {
    const panel = panelRef.current
    if (!open || !panel) return
    const index = messages.findIndex((message) => message.id === (scrollTargetId ?? activeId))
    const row = panel.children[index] as HTMLElement | undefined
    if (row) panel.scrollTop = Math.max(0, row.offsetTop - panel.clientHeight / 2 + row.clientHeight / 2)
  }, [open, scrollTargetId, activeId, messages])

  if (messages.length < 2) return null

  return (
    <div
      className="absolute inset-y-3 left-2 z-10 hidden w-9 md:block"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => { setOpen(false); setPreviewId(null); setScrollTargetId(null) }}
      onFocusCapture={() => setOpen(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false)
      }}
    >
      <nav ref={railRef} aria-label="会话消息导航" className="flex h-full w-9 flex-col overflow-y-auto overscroll-contain py-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <div className="my-auto flex w-full shrink-0 flex-col gap-1">
          {messages.map((message, index) => {
            const active = message.id === activeId
            return (
              <button
                key={message.id}
                ref={active ? activeRef : undefined}
                type="button"
                aria-label={`跳转到第 ${index + 1} 条消息`}
                aria-current={active ? "location" : undefined}
                onMouseEnter={() => { setPreviewId(message.id); setScrollTargetId(message.id) }}
                onFocus={() => { setPreviewId(message.id); setScrollTargetId(message.id) }}
                onClick={() => scrollToMessage(message.id, { align: "start", behavior: "smooth" })}
                className="group flex h-2 w-9 shrink-0 items-center justify-start rounded-sm focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
              >
                <span className={`h-0.5 rounded-full transition-all ${active ? "w-8 bg-foreground" : message.role === "user" ? "w-4 bg-muted-foreground/45 group-hover:w-7 group-hover:bg-foreground" : "w-3 bg-muted-foreground/30 group-hover:w-7 group-hover:bg-foreground"}`} />
              </button>
            )
          })}
        </div>
      </nav>
      {open && (
        <div className="absolute left-full top-1/2 w-80 max-w-[calc(100vw-5rem)] -translate-y-1/2 pl-2">
          <div ref={panelRef} aria-label="会话消息预览" className="relative max-h-[min(28rem,calc(100vh-7rem))] overflow-y-auto rounded-2xl border bg-popover p-3 text-popover-foreground shadow-lg">
            {messages.map((message, index) => (
              <button
                key={message.id}
                type="button"
                onMouseEnter={() => setPreviewId(message.id)}
                onClick={() => scrollToMessage(message.id, { align: "start", behavior: "smooth" })}
                className={`flex w-full items-center gap-3 rounded-lg px-2 py-2 text-sm hover:bg-muted ${message.id === (previewId ?? activeId) ? "text-foreground" : "text-muted-foreground"}`}
              >
                <span className={`min-w-0 flex-1 truncate ${message.role === "user" ? "text-right" : "text-left"}`}>{messagePreview(message)}</span>
                <span aria-hidden="true" className={`h-0.5 shrink-0 rounded-full ${message.id === (previewId ?? activeId) ? "w-3 bg-foreground" : "w-2 bg-muted-foreground/35"}`} />
                <span className="sr-only">跳转到第 {index + 1} 条消息</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
