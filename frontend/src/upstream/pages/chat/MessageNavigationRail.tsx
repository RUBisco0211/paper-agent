import { getTextContent, type Msg } from "@agentscope-ai/agentscope/message"
import { useEffect, useRef } from "react"

import { useMessageScroller, useMessageScrollerVisibility } from "@upstream/components/ui/message-scroller"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@upstream/components/ui/tooltip"

function messagePreview(message: Msg): string {
  const text = getTextContent(message)?.replace(/\s+/g, " ").trim()
  if (!text) return "暂无文字内容"
  return text.length > 140 ? `${text.slice(0, 140)}…` : text
}

export function MessageNavigationRail({ messages }: { messages: Msg[] }) {
  const { scrollToMessage } = useMessageScroller()
  const { currentAnchorId, visibleMessageIds } = useMessageScrollerVisibility()
  const railRef = useRef<HTMLElement>(null)
  const activeRef = useRef<HTMLButtonElement>(null)
  const activeId = currentAnchorId ?? visibleMessageIds[0] ?? messages.at(-1)?.id

  useEffect(() => {
    const rail = railRef.current
    const active = activeRef.current
    if (!rail || !active) return
    const top = active.offsetTop - rail.offsetTop
    if (top < rail.scrollTop) rail.scrollTop = top
    else if (top + active.offsetHeight > rail.scrollTop + rail.clientHeight) {
      rail.scrollTop = top + active.offsetHeight - rail.clientHeight
    }
  }, [activeId, messages.length])

  if (messages.length < 2) return null

  return <TooltipProvider>
    <nav ref={railRef} aria-label="会话消息导航" className="absolute inset-y-3 left-2 z-10 hidden w-9 flex-col justify-between gap-1 overflow-y-auto overscroll-contain py-1 [scrollbar-width:none] md:flex [&::-webkit-scrollbar]:hidden">
      {messages.map((message, index) => {
        const active = message.id === activeId
        return <Tooltip key={message.id}>
          <TooltipTrigger asChild>
            <button
              ref={active ? activeRef : undefined}
              type="button"
              aria-label={`跳转到第 ${index + 1} 条消息`}
              aria-current={active ? "location" : undefined}
              onClick={() => scrollToMessage(message.id, { align: "start", behavior: "smooth" })}
              className="group flex h-2 w-9 shrink-0 items-center justify-start rounded-sm focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
            >
              <span className={`h-0.5 rounded-full transition-all ${active ? "w-8 bg-foreground" : message.role === "user" ? "w-4 bg-muted-foreground/45 group-hover:w-7 group-hover:bg-foreground" : "w-3 bg-muted-foreground/30 group-hover:w-7 group-hover:bg-foreground"}`} />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={12} className="w-72 max-w-[min(18rem,calc(100vw-5rem))] rounded-xl border bg-popover p-3 text-popover-foreground shadow-lg [&_svg]:fill-popover [&_svg]:bg-popover">
            <p className="mb-1 font-medium">{message.role === "user" ? "我" : message.role === "assistant" ? "助手" : "消息"}</p>
            <p className="line-clamp-3 break-words text-muted-foreground">{messagePreview(message)}</p>
          </TooltipContent>
        </Tooltip>
      })}
    </nav>
  </TooltipProvider>
}
