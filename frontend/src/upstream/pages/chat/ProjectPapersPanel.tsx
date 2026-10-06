import { useQuery } from "@tanstack/react-query"
import { FileText, PanelRightClose, PanelRightOpen, Plus } from "lucide-react"
import { useState } from "react"

import { AddPapersDialog } from "@/components/projects/add-papers-dialog"
import { PaperDetailSheet } from "@/components/papers/paper-detail-sheet"
import { useApi } from "@/lib/api/provider"
import { Button } from "@upstream/components/ui/button"

export function ProjectPapersPanel({ projectId }: { projectId: string }) {
  const { api } = useApi()
  const [open, setOpen] = useState(true)
  const [paperId, setPaperId] = useState<string | null>(null)
  const project = useQuery({ queryKey: ["project", projectId], queryFn: () => api.projects.detail(projectId) })
  const papers = useQuery({ queryKey: ["project-papers", projectId], queryFn: () => api.projects.papers(projectId, { limit: 200 }) })
  const items = papers.data?.items ?? []

  return <>
    <Button variant="ghost" size="icon-sm" aria-label={open ? "收起项目文献" : "展开项目文献"} onClick={() => setOpen(!open)} className="self-start">{open ? <PanelRightClose /> : <PanelRightOpen />}</Button>
    {open && <aside aria-label="项目文献" className="flex w-64 shrink-0 flex-col overflow-hidden border-l bg-background">
      <header className="flex items-center justify-between border-b px-4 py-3"><span className="truncate font-medium">{project.data?.name ?? "项目文献"}</span>
        <AddPapersDialog projectId={projectId} existingPaperIds={items.map((item) => item.id)} trigger={<Button variant="ghost" size="icon-sm" aria-label="添加文献"><Plus /></Button>} />
      </header>
      <div className="flex-1 overflow-y-auto p-2">
        {papers.isPending && <p className="p-2 text-sm text-muted-foreground">加载中…</p>}
        {papers.isError && <p role="alert" className="p-2 text-sm text-destructive">无法读取项目文献</p>}
        {papers.isSuccess && items.length === 0 && <p className="p-2 text-sm text-muted-foreground">暂无文献</p>}
        {items.map((item) => <button key={item.id} type="button" onClick={() => setPaperId(item.id)} className="flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-muted"><FileText className="mt-0.5 size-4 shrink-0" /><span className="line-clamp-2">{item.title || item.original_filename || "未命名文献"}</span></button>)}
      </div>
    </aside>}
    <PaperDetailSheet paperId={paperId} onOpenChange={(next) => !next && setPaperId(null)} />
  </>
}
