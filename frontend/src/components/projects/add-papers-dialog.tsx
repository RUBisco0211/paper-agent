import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useMemo, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@upstream/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@upstream/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Spinner } from "@/components/ui/spinner"
import { useApi } from "@/lib/api/provider"
import { notifyError, notifySuccess } from "@/lib/errors"
import { queryKeys } from "@/app/query"

/**
 * Add papers from the personal library.
 *
 * Papers without full text can be added: they can be listed and read
 * bibliographically, they just never become retrieval evidence.
 */
export function AddPapersDialog({
  projectId,
  existingPaperIds,
  trigger,
  open: openProp,
  onOpenChange,
}: {
  projectId: string
  existingPaperIds: string[]
  trigger?: React.ReactNode
  open?: boolean
  onOpenChange?: (open: boolean) => void
}) {
  const { api } = useApi()
  const queryClient = useQueryClient()
  const [openState, setOpenState] = useState(false)
  const open = openProp ?? openState
  const setOpen = onOpenChange ?? setOpenState
  const [query, setQuery] = useState("")
  const [selected, setSelected] = useState<string[]>([])

  const library = useQuery({
    queryKey: queryKeys.papers({ q: query, limit: 200 }),
    queryFn: () => api.library.list({ q: query || undefined, limit: 200 }),
    enabled: open,
  })

  const existing = useMemo(() => new Set(existingPaperIds), [existingPaperIds])
  const candidates = (library.data?.items ?? []).filter((item) => !existing.has(item.id))

  const add = useMutation({
    mutationFn: () => api.projects.addPapers(projectId, selected),
    onSuccess: (result) => {
      notifySuccess(
        `已加入 ${result.added.length} 篇文献`,
        result.already_present.length
          ? `${result.already_present.length} 篇此前已存在`
          : undefined,
      )
      setSelected([])
      setOpen(false)
      void queryClient.invalidateQueries({ queryKey: ["project-papers"] })
      void queryClient.invalidateQueries({ queryKey: ["project"] })
      void queryClient.invalidateQueries({ queryKey: ["projects"] })
    },
    onError: (error) => notifyError(error, "加入项目失败"),
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) {
          setSelected([])
        }
      }}
    >
      <DialogTrigger asChild>{trigger ?? <Button variant="outline">添加文献</Button>}</DialogTrigger>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>从文献库添加</DialogTitle>
        </DialogHeader>
        <Input
          aria-label="搜索文献"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <ScrollArea className="h-72 rounded-md border">
          {library.isPending ? (
            <p className="text-muted-foreground p-4 text-sm">加载中…</p>
          ) : candidates.length === 0 ? (
            <p className="text-muted-foreground p-4 text-sm">
              没有可添加的文献（可能都已在该项目中）。
            </p>
          ) : (
            <ul className="flex flex-col">
              {candidates.map((paper) => (
                <li
                  key={paper.id}
                  className="hover:bg-accent/50 flex items-start gap-3 border-b p-3 last:border-b-0"
                >
                  <Checkbox
                    id={`paper-${paper.id}`}
                    checked={selected.includes(paper.id)}
                    onCheckedChange={(checked) =>
                      setSelected((prev) =>
                        checked ? [...prev, paper.id] : prev.filter((id) => id !== paper.id),
                      )
                    }
                  />
                  <label htmlFor={`paper-${paper.id}`} className="flex-1 cursor-pointer">
                    <p className="text-sm font-medium">
                      {paper.title ?? paper.original_filename ?? "未命名条目"}
                    </p>
                    <p className="text-muted-foreground text-xs">
                      {paper.authors.slice(0, 3).join("、") || "作者未知"}
                    </p>
                    <div className="mt-1 flex gap-1">
                      {paper.capabilities.has_fulltext ? (
                        <Badge variant="secondary">可检索全文</Badge>
                      ) : (
                        <Badge variant="outline">待补全文</Badge>
                      )}
                    </div>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </ScrollArea>
        <DialogFooter>
          <Button
            disabled={selected.length === 0 || add.isPending}
            onClick={() => add.mutate()}
          >
            {add.isPending ? <Spinner data-icon="inline-start" /> : null}
            添加文献
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
