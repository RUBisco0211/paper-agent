import * as React from "react"
import { FileText, LoaderCircle, X } from "lucide-react"
import { cn } from "cn"

import { Button } from "@/components/ui/button"

function Attachment({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="attachment"
      className={cn(
        "bg-muted/50 flex min-w-0 items-center gap-2 rounded-lg border px-3 py-2 text-sm",
        className,
      )}
      {...props}
    />
  )
}

function AttachmentIcon({ pending = false }: { pending?: boolean }) {
  return pending ? (
    <LoaderCircle className="animate-spin" aria-hidden="true" />
  ) : (
    <FileText aria-hidden="true" />
  )
}

function AttachmentContent({
  name,
  detail,
}: {
  name: string
  detail?: string
}) {
  return (
    <div className="min-w-0 flex-1">
      <p className="truncate font-medium">{name}</p>
      {detail ? <p className="text-muted-foreground truncate text-xs">{detail}</p> : null}
    </div>
  )
}

function AttachmentRemove({ onClick }: { onClick: () => void }) {
  return (
    <Button type="button" variant="ghost" size="icon-sm" aria-label="移除附件" onClick={onClick}>
      <X />
    </Button>
  )
}

export { Attachment, AttachmentContent, AttachmentIcon, AttachmentRemove }
