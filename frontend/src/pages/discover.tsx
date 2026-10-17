import { useQuery, useQueryClient } from "@tanstack/react-query"
import { ExternalLink, Search } from "lucide-react"
import { useState, type FormEvent } from "react"

import { queryKeys } from "@/app/query"
import type { ExternalDiscoveryResponse, ExternalPaperCandidate } from "@/lib/api/types"
import { useApi } from "@/lib/api/provider"
import { describeError, notifySuccess } from "@/lib/errors"
import { useImportQueue } from "@/lib/import-queue-context"
import { Button } from "@upstream/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@upstream/components/ui/dialog"
import { Input } from "@upstream/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@upstream/components/ui/select"
import { Spinner } from "@upstream/components/ui/spinner"

const sourceNames: Record<string, string> = {
  openalex: "OpenAlex",
  semantic_scholar: "Semantic Scholar",
  crossref: "Crossref",
}

export function DiscoverPage() {
  const { api } = useApi()
  const queryClient = useQueryClient()
  const { setOpen: setQueueOpen } = useImportQueue()
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<ExternalDiscoveryResponse | null>(null)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState("")
  const [selected, setSelected] = useState<string[]>([])
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [targetProject, setTargetProject] = useState("none")
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState("")
  const projects = useQuery({
    queryKey: queryKeys.projects({ limit: 100 }),
    queryFn: () => api.projects.list({ limit: 100 }),
    enabled: confirmOpen,
  })

  async function searchPapers(event: FormEvent) {
    event.preventDefault()
    const text = query.trim()
    if (!text) return
    setSearching(true)
    setSearchError("")
    setImportError("")
    setResults(null)
    setSelected([])
    try {
      setResults(await api.retrieval.discover(text, 20))
    } catch (error) {
      setSearchError(describeError(error))
    } finally {
      setSearching(false)
    }
  }

  const chosen = (results?.papers ?? []).filter((paper) => selected.includes(paper.source_id) && paper.doi)

  async function importSelected() {
    if (!chosen.length) return
    setImporting(true)
    setImportError("")
    const unique = [...new Map(chosen.map((paper) => [paper.doi!.toLowerCase(), paper])).values()]
    const outcomes = await Promise.allSettled(unique.map((paper) =>
      api.imports.start(paper.doi!, targetProject === "none" ? {} : { project_id: targetProject }),
    ))
    const failed = unique.filter((_, index) => outcomes[index].status === "rejected")
    const succeeded = outcomes.length - failed.length
    if (succeeded > 0) {
      void queryClient.invalidateQueries({ queryKey: ["import-queue"] })
      notifySuccess(`${succeeded} 篇文献已加入入库队列`)
      setQueueOpen(true)
    }
    if (failed.length) {
      setSelected(failed.map((paper) => paper.source_id))
      setImportError(`${failed.length} 篇文献未能加入队列，请重试`)
    } else {
      setSelected([])
      setConfirmOpen(false)
    }
    setImporting(false)
  }

  return <>
    <header data-slot="app-toolbar" className="flex h-(--app-toolbar-height) shrink-0 items-center border-b px-6"><h1 className="text-lg font-semibold">在线检索文献</h1></header>
    <div className="mx-auto w-full max-w-5xl space-y-5 px-6 py-6">
      <form onSubmit={searchPapers} className="flex gap-2">
        <Input type="search" aria-label="搜索文献" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="标题或关键词" maxLength={300} />
        <Button type="submit" disabled={!query.trim() || searching}>{searching ? <Spinner data-icon="inline-start" /> : <Search data-icon="inline-start" />}搜索</Button>
      </form>
      {searchError && <p role="alert" className="text-sm text-destructive">{searchError}</p>}
      {results?.failed_sources.length ? <p className="text-sm text-muted-foreground">部分来源暂不可用：{results.failed_sources.map((name) => sourceNames[name] ?? name).join("、")}</p> : null}
      {results && !results.papers.length && <p className="py-12 text-center text-sm text-muted-foreground">没有找到相关文献</p>}
      {results && results.papers.length > 0 && <>
        <div className="flex items-center justify-between"><p className="text-sm text-muted-foreground">找到 {results.papers.length} 篇文献</p><Button disabled={!selected.length} onClick={() => setConfirmOpen(true)}>选择入库（{selected.length}）</Button></div>
        <div className="divide-y border-y">{results.papers.map((paper) => <CandidateRow key={paper.source_id} paper={paper} selected={selected.includes(paper.source_id)} disabled={!paper.doi || (selected.length >= 10 && !selected.includes(paper.source_id))} toggle={() => setSelected((before) => before.includes(paper.source_id) ? before.filter((id) => id !== paper.source_id) : [...before, paper.source_id])} />)}</div>
      </>}
    </div>
    <Dialog open={confirmOpen} onOpenChange={(open) => { if (!importing) setConfirmOpen(open) }}><DialogContent className="sm:max-w-lg">
      <DialogHeader><DialogTitle>导入所选文献</DialogTitle><DialogDescription>将 {chosen.length} 篇文献加入入库队列。</DialogDescription></DialogHeader>
      <div className="space-y-2"><label className="text-sm font-medium" htmlFor="import-target">入库范围</label>
        <Select value={targetProject} onValueChange={setTargetProject}><SelectTrigger id="import-target" aria-label="入库范围"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">全局</SelectItem>{projects.data?.items.map((project) => <SelectItem key={project.id} value={project.id}>{project.name}</SelectItem>)}</SelectContent></Select>
        {projects.isError && <p role="alert" className="text-sm text-destructive">项目列表加载失败，仍可选择全局入库</p>}
        {importError && <p role="alert" className="text-sm text-destructive">{importError}</p>}
      </div>
      <DialogFooter><Button variant="outline" onClick={() => setConfirmOpen(false)} disabled={importing}>取消</Button><Button onClick={() => void importSelected()} disabled={!chosen.length || importing || (targetProject !== "none" && (projects.isLoading || projects.isError))}>{importing ? <Spinner data-icon="inline-start" /> : null}确认导入</Button></DialogFooter>
    </DialogContent></Dialog>
  </>
}

function CandidateRow({ paper, selected, disabled, toggle }: { paper: ExternalPaperCandidate; selected: boolean; disabled: boolean; toggle: () => void }) {
  return <div className="flex gap-3 py-4">
    <input type="checkbox" aria-label={paper.title} className="mt-1 size-4" checked={selected} disabled={disabled} onChange={toggle} />
    <div className="min-w-0 flex-1 space-y-1">
      <p className="font-medium">{paper.title}</p>
      {paper.authors?.length ? <p className="truncate text-sm text-muted-foreground">{paper.authors.join("、")}</p> : null}
      <p className="text-xs text-muted-foreground">{paper.year ?? ""}{paper.sources?.length ? ` · ${paper.sources.map((name) => sourceNames[name] ?? name).join("、")}` : ""}{!paper.doi ? " · 暂无可导入的 DOI" : ""}</p>
      <div className="flex gap-4 text-sm">{paper.doi && <a className="underline" href={`https://doi.org/${paper.doi}`} target="_blank" rel="noopener noreferrer">DOI {paper.doi}</a>}{paper.pdf_url?.startsWith("https://") && <a className="inline-flex items-center gap-1 underline" href={paper.pdf_url} target="_blank" rel="noopener noreferrer">PDF <ExternalLink className="size-3" /></a>}{paper.url?.startsWith("https://") && <a className="underline" href={paper.url} target="_blank" rel="noopener noreferrer">来源</a>}</div>
    </div>
  </div>
}
