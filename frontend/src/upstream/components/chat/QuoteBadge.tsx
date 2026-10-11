import { X } from 'lucide-react'
import { useState } from 'react'
import { HoverCard as HoverCardPrimitive } from 'radix-ui'

import type { QuoteReference } from './quote-references'
import { Badge } from '@upstream/components/ui/badge'
import { Button } from '@upstream/components/ui/button'
import {
  Popover, PopoverAnchor, PopoverContent, PopoverDescription,
  PopoverHeader, PopoverTitle,
} from '@upstream/components/ui/popover'
import { Textarea } from '@upstream/components/ui/textarea'

export function QuoteBadge({ reference, onOpen, onRemove, onEdit }: {
  reference: QuoteReference
  onOpen?: () => void
  onRemove?: () => void
  onEdit?: (comment: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [draft, setDraft] = useState(reference.comment)
  const label = reference.kind === 'message' ? '消息引用' : reference.kind === 'parsed_block' ? '文献块引用' : '文献原文引用'
  const excerpt = reference.selected_text || (reference.kind === 'parsed_block' && reference.include_image ? '图片或图表' : '')

  const setOpen = (open: boolean) => {
    if (open) setDraft(reference.comment)
    setEditing(open)
  }

  return <Popover open={editing} onOpenChange={setOpen}>
    <PopoverAnchor asChild>
      <Badge data-quote-badge variant="outline" className="max-w-64 gap-0 border-[var(--message-quote-accent)] px-1 font-normal">
        <HoverCardPrimitive.Root openDelay={250} closeDelay={120} open={hovered && !editing} onOpenChange={setHovered}>
          <HoverCardPrimitive.Trigger asChild>
            <button type="button" className="max-w-52 truncate px-1 py-0.5 text-left hover:text-primary"
              aria-label={`${onEdit ? '编辑' : '查看'}${label}`}
              onClick={onEdit ? () => setOpen(true) : onOpen}>
              {label} · {excerpt}
            </button>
          </HoverCardPrimitive.Trigger>
          <HoverCardPrimitive.Portal>
            <HoverCardPrimitive.Content side="top" align="start" sideOffset={8}
              className="z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2 rounded-lg bg-popover p-3 text-sm text-popover-foreground shadow-md ring-1 ring-foreground/10 outline-hidden data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0">
              <p className="text-xs font-medium text-muted-foreground">{label}</p>
              <p className="max-h-32 overflow-y-auto whitespace-pre-wrap wrap-break-word">{excerpt}</p>
              {reference.comment && <p className="border-t pt-2 whitespace-pre-wrap wrap-break-word">{reference.comment}</p>}
            </HoverCardPrimitive.Content>
          </HoverCardPrimitive.Portal>
        </HoverCardPrimitive.Root>
        {onRemove && <Button type="button" variant="ghost" size="icon-xs" aria-label="移除引用" title="移除引用" onClick={onRemove}><X /></Button>}
      </Badge>
    </PopoverAnchor>
    {onEdit && <PopoverContent align="start" side="top" className="w-80 max-w-[calc(100vw-2rem)]">
      <PopoverHeader>
        <PopoverTitle>编辑引用评论</PopoverTitle>
        <PopoverDescription className="line-clamp-3">{excerpt}</PopoverDescription>
      </PopoverHeader>
      <Textarea aria-label="编辑引用评论" maxLength={2000} value={draft} onChange={(event) => setDraft(event.target.value)} />
      <div className="flex justify-end">
        <Button size="sm" onClick={() => { onEdit(draft.trim()); setEditing(false) }}>保存评论</Button>
      </div>
    </PopoverContent>}
  </Popover>
}
