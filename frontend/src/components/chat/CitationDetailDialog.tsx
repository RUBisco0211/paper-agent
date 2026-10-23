import { Button } from "@/components/ui/Button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/Dialog"

export type CitationBlock = {
  block_id: number
  page?: number | null
}

function pageSummary(blocks: CitationBlock[]): string {
  const pages = new Set(blocks.map((block) => block.page).filter((page): page is number => typeof page === "number"))
  const parts = [`证据包含 ${blocks.length} 个段落`]
  if (pages.size) parts.push(`分布在 ${pages.size} 页`)
  return parts.join("，")
}

/** Lists the original blocks behind one citation so the reader can pick where to land. */
export function CitationDetailDialog({
  open,
  blocks,
  snippet,
  onOpenChange,
  onOpenBlock,
}: {
  open: boolean
  blocks: CitationBlock[]
  snippet?: string
  onOpenChange: (open: boolean) => void
  onOpenBlock: (blockId: number, page?: number | null) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>引用详情</DialogTitle>
          <DialogDescription>{pageSummary(blocks)}</DialogDescription>
        </DialogHeader>
        {snippet && (
          <p className="max-h-32 overflow-y-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-sm">{snippet}</p>
        )}
        <ol className="max-h-[50vh] space-y-2 overflow-y-auto">
          {blocks.map((block, index) => (
            <li key={block.block_id}>
              <Button
                type="button"
                variant="outline"
                className="w-full justify-between"
                onClick={() => onOpenBlock(block.block_id, block.page)}
              >
                <span>第 {index + 1} 段{block.page ? ` · 原文第 ${block.page} 页` : ""}</span>
                <span className="text-muted-foreground">定位</span>
              </Button>
            </li>
          ))}
        </ol>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>关闭</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
