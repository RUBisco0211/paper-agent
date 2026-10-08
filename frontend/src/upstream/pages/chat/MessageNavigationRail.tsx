import { getTextContent, type Msg } from "@agentscope-ai/agentscope/message"
import { useEffect, useRef, useState } from "react"

import { useMessageScroller, useMessageScrollerVisibility } from "@upstream/components/ui/message-scroller"

function messagePreview(message: Msg): string {
  const content = getTextContent(message)?.replace(/\s+/g, " ").trim()
  if (!content) return "暂无文字内容"
  return content.length > 140 ? `${content.slice(0, 140)}…` : content
}

export function MessageNavigationRail({ messages }: { messages: Msg[] }) {
  const { scrollToMessage } = useMessageScroller()
  const { currentAnchorId, visibleMessageIds } = useMessageScrollerVisibility()
  const [open, setOpen] = useState(false)
  const [previewId, setPreviewId] = useState<string | null>(null)
  const railRef = useRef<HTMLElement>(null)
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

  if (messages.length < 2) return null

  return (
    <div
      className={`absolute right-2 top-1/2 z-10 hidden max-h-[calc(100%-1.5rem)] -translate-y-1/2 md:block ${open ? "w-64 max-w-[calc(100vw-3rem)] rounded-2xl border bg-popover p-2 text-popover-foreground shadow-lg" : "w-8"}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => { setOpen(false); setPreviewId(null) }}
      onFocusCapture={() => setOpen(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false)
      }}
    >
      <nav ref={railRef} aria-label="会话消息导航" className="max-h-[min(18rem,calc(100vh-7rem))] overflow-y-auto overscroll-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {messages.map((message, index) => {
          const active = message.id === activeId
          const highlighted = message.id === (previewId ?? activeId)
          return (
            <button
              key={message.id}
              ref={active ? activeRef : undefined}
              type="button"
              aria-label={`跳转到第 ${index + 1} 条消息`}
              aria-current={active ? "location" : undefined}
              onMouseEnter={() => setPreviewId(message.id)}
              onFocus={() => setPreviewId(message.id)}
              onClick={() => scrollToMessage(message.id, { align: "start", behavior: "smooth" })}
              className={`group flex h-6 w-full shrink-0 flex-row-reverse items-center gap-2 rounded-lg px-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring ${open && highlighted ? "bg-muted" : ""}`}
            >
              <span aria-hidden="true" className={`h-0.5 w-2 shrink-0 rounded-full ${highlighted ? "bg-foreground" : "bg-muted-foreground/35"}`} />
              {open && <span className={`min-w-0 flex-1 truncate text-right ${highlighted ? "text-foreground" : "text-muted-foreground"}`}>{messagePreview(message)}</span>}
            </button>
          )
        })}
      </nav>
    </div>
  )
}
