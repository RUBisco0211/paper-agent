import { useQuery } from "@tanstack/react-query"
import { FileText, Plus } from "lucide-react"
import { useLocation, useNavigate } from "react-router-dom"

import { AddPapersDialog } from "@/components/projects/add-papers-dialog"
import { useApi } from "@/lib/api/provider"
import { Button } from "@upstream/components/ui/button"

export function ProjectPapersPanel({ projectId }: { projectId: string }) {
  const { api } = useApi()
  const navigate = useNavigate()
  const location = useLocation()
  const project = useQuery({ queryKey: ["project", projectId], queryFn: () => api.projects.detail(projectId) })
  const papers = useQuery({ queryKey: ["project-papers", projectId], queryFn: () => api.projects.papers(projectId, { limit: 200 }) })
  const items = papers.data?.items ?? []

  return <aside aria-label="项目文献" className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
      <header className="flex h-16 shrink-0 items-center justify-between border-b px-4"><span className="truncate font-medium">{project.data?.name ?? "项目文献"}</span>
        <AddPapersDialog projectId={projectId} existingPaperIds={items.map((item) => item.id)} trigger={<Button variant="ghost" size="icon-sm" aria-label="添加文献"><Plus /></Button>} />
      </header>
      <div className="flex-1 overflow-y-auto p-2">
        {papers.isPending && <p className="p-2 text-sm text-muted-foreground">加载中…</p>}
        {papers.isError && <p role="alert" className="p-2 text-sm text-destructive">无法读取项目文献</p>}
        {papers.isSuccess && items.length === 0 && <p className="p-2 text-sm text-muted-foreground">暂无文献</p>}
        {items.map((item) => <button key={item.id} type="button" onClick={() => navigate(`/library/${item.id}`, { state: { from: location.pathname } })} className="flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-muted"><FileText className="mt-0.5 size-4 shrink-0" /><span className="line-clamp-2">{item.title || item.original_filename || "未命名文献"}</span></button>)}
      </div>
    </aside>
}
