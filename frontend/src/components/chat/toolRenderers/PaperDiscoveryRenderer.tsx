import { createContext, useContext, useState } from "react"
import { Button } from "@/components/ui/Button"
import { Checkbox } from "@/components/ui/Checkbox"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/Dialog"
import { getResultText } from "@/components/chat/toolRenderers/shared"
import type { ExternalPaperCandidate } from "@/types/business"
import type { ToolCallWithResult, ToolRenderer } from "./types"

type Candidate = ExternalPaperCandidate & { candidate_token?: string }
const sourceNames: Record<string, string> = { openalex: "OpenAlex", semantic_scholar: "Semantic Scholar", crossref: "Crossref" }
export const DiscoveryImportContext = createContext<((tokens: string[]) => Promise<void>) | null>(null)

function candidatesOf(pair: ToolCallWithResult): { papers: Candidate[]; failedSources: string[] } {
  try {
    const data: unknown = JSON.parse(getResultText(pair.result))
    if (!data || typeof data !== "object" || !("papers" in data) || !Array.isArray(data.papers)) return { papers: [], failedSources: [] }
    return { papers: data.papers.filter((item): item is Candidate => Boolean(item && typeof item.source_id === "string" && typeof item.title === "string")), failedSources: "failed_sources" in data && Array.isArray(data.failed_sources) ? data.failed_sources.filter((name): name is string => typeof name === "string") : [] }
  } catch { return { papers: [], failedSources: [] } }
}

function DiscoveryResults({ pair }: { pair: ToolCallWithResult }) {
  const { papers: candidates, failedSources } = candidatesOf(pair)
  const onImport = useContext(DiscoveryImportContext)
  const [selected, setSelected] = useState<string[]>([])
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  if (pair.result?.state === "error") return <p className="p-3 text-sm text-destructive">在线检索失败，请重试</p>
  if (!candidates.length) return <p className="p-3 text-sm text-muted-foreground">{failedSources.length ? `部分来源暂不可用：${failedSources.map((name) => sourceNames[name] ?? name).join("、")}。没有找到相关文献` : "没有找到相关文献"}</p>
  const valid = candidates.filter((item) => item.candidate_token)
  const tokens = valid.filter((item) => selected.includes(item.source_id)).map((item) => item.candidate_token!)
  return <div className="space-y-2 py-2">
    {failedSources.length > 0 && <p className="text-xs text-muted-foreground">部分来源暂不可用：{failedSources.map((name) => sourceNames[name] ?? name).join("、")}</p>}
    {candidates.map((item) => <label key={item.source_id} className="flex cursor-pointer items-start gap-2 rounded-lg border p-3 text-sm">
      <Checkbox
        className="mt-1"
        aria-label={item.title ?? item.source_id}
        disabled={!item.candidate_token || !onImport}
        checked={selected.includes(item.source_id)}
        onCheckedChange={(checked) =>
          setSelected((before) =>
            checked === true
              ? [...before, item.source_id]
              : before.filter((id) => id !== item.source_id),
          )
        }
      />
      <span className="min-w-0"><span className="block font-medium">{item.title}</span><span className="text-xs text-muted-foreground">{item.year ?? ""}{item.doi ? ` · DOI ${item.doi}` : " · 暂无可导入标识符"}{item.sources?.length ? ` · ${item.sources.map((name) => sourceNames[name] ?? name).join("、")}` : ""}</span><span className="block text-xs">{item.pdf_url?.startsWith("https://") && <a href={item.pdf_url} target="_blank" rel="noopener noreferrer" onClick={(event) => event.stopPropagation()} className="mr-3 underline">PDF</a>}{item.url?.startsWith("https://") && <a href={item.url} target="_blank" rel="noopener noreferrer" onClick={(event) => event.stopPropagation()} className="underline">来源</a>}</span></span>
    </label>)}
    {onImport && <Button size="sm" disabled={!tokens.length} onClick={() => setConfirm(true)}>选择入库（{tokens.length}）</Button>}
    <Dialog open={confirm} onOpenChange={setConfirm}><DialogContent className="sm:max-w-md">
      <DialogHeader><DialogTitle>导入所选文献</DialogTitle><DialogDescription>Agent 将按已选标识符批量入库，结果显示在入库队列。</DialogDescription></DialogHeader>
      <p className="text-sm">已选 {tokens.length} 篇文献</p>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <DialogFooter><Button variant="outline" onClick={() => setConfirm(false)}>取消</Button><Button disabled={busy || !onImport} onClick={async () => { if (!onImport) return; setBusy(true); setError(""); try { await onImport(tokens); setConfirm(false) } catch (cause) { setError(cause instanceof Error ? cause.message : "授权失败") } finally { setBusy(false) } }}>确认导入</Button></DialogFooter>
    </DialogContent></Dialog>
  </div>
}

export const PaperDiscoveryRenderer: ToolRenderer = {
  renderHeader: () => <span>在线检索文献</span>,
  renderBody: (pair) => pair.result ? <DiscoveryResults pair={pair} /> : null,
}
