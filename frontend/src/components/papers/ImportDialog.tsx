import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router-dom"

import { Button } from "@/components/ui/Button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/Dialog"
import { Input } from "@/components/ui/Input"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/Field"
import { Label } from "@/components/ui/Label"
import { Spinner } from "@/components/ui/Spinner"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select"
import type { PaperImport } from "@/lib/api"
import { useApi } from "@/components/providers/ApiProvider"
import { describeError, notifySuccess } from "@/lib/errors"
import { queryKeys } from "@/app/query"

const STATUS_TEXT: Record<PaperImport["status"], string> = {
  queued: "排队中…",
  running: "正在入库…",
  ready: "已入库",
  source_unavailable: "没有找到可用的源文件",
  failed: "入库失败",
}

const ERROR_TEXT: Record<string, string> = {
  metadata_not_found: "没有查询到该标识符对应的文献",
  metadata_provider_failed: "元数据服务暂时不可用，可稍后重试",
  provider_rate_limited: "来源限流，请稍后重试",
  paper_pdf_not_available: "来源没有提供公开可用的 PDF",
  import_source_unavailable: "没有找到可用的源文件",
  identifier_invalid: "只支持 DOI 或 arXiv 标识符及其规范链接",
}

/** DOI/arXiv import: fetch the source file, then parse it. */
export function ImportDialog({
  projectId,
  onImported,
  trigger,
}: {
  projectId?: string
  onImported?: (result: PaperImport) => void
  trigger?: React.ReactNode
}) {
  const { api } = useApi()
  const [open, setOpen] = useState(false)
  const [identifier, setIdentifier] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<PaperImport | null>(null)

  const projects = useQuery({
    queryKey: queryKeys.projects({ limit: 100 }),
    queryFn: () => api.projects.list({ limit: 100 }),
    enabled: open && !projectId,
  })
  const [targetProject, setTargetProject] = useState<string>(projectId ?? "none")

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const started = await api.imports.start(identifier.trim(), {
        project_id: projectId ?? (targetProject === "none" ? undefined : targetProject),
      })
      setResult(started)
      await pollUntilSettled(started.id, setResult)
      notifySuccess("导入已受理")
      onImported?.(started)
    } catch (cause) {
      setError(describeError(cause))
    } finally {
      setBusy(false)
    }
  }

  async function pollUntilSettled(
    importId: string,
    update: (job: PaperImport) => void,
  ): Promise<void> {
    const terminal = new Set(["ready", "pdf_unavailable", "failed"])
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const job = await api.imports.status(importId)
      update(job)
      if (terminal.has(job.status)) {
        return
      }
      await new Promise((resolve) => setTimeout(resolve, 1000))
    }
  }

  function handleOpenChange(next: boolean) {
    setOpen(next)
    if (!next) {
      setResult(null)
      setError(null)
      setIdentifier("")
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        {trigger ?? <Button variant="outline">按 DOI/arXiv 导入</Button>}
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>按标识符导入文献</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="identifier">DOI 或 arXiv</FieldLabel>
              <Input
                id="identifier"
                value={identifier}
                placeholder="10.1145/3290605.3300233"
                onChange={(event) => setIdentifier(event.target.value)}
                required
              />
            </Field>
          </FieldGroup>
          {!projectId && (projects.data?.items.length ?? 0) > 0 ? (
            <div className="flex flex-col gap-2">
              <Label htmlFor="target-project">同时加入项目（可选）</Label>
              <Select value={targetProject} onValueChange={setTargetProject}>
                <SelectTrigger id="target-project" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="none">不加入项目</SelectItem>
                    {projects.data?.items.map((project) => (
                      <SelectItem key={project.id} value={project.id}>
                        {project.name}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
          ) : null}
          {error ? <p className="text-destructive text-sm">{error}</p> : null}
          {result ? (
            <div className="bg-muted/50 rounded-md p-3 text-sm">
              <p className="font-medium">{STATUS_TEXT[result.status]}</p>
              {result.error_code ? (
                <p className="text-muted-foreground mt-1">
                  {ERROR_TEXT[result.error_code] ?? result.error_code}
                </p>
              ) : null}
              {result.paper_id ? (
                <p className="mt-2">
                  条目已入库：
                  <Link
                    className="underline"
                    to="/library"
                    onClick={() => handleOpenChange(false)}
                  >
                    在文献库中查看
                  </Link>
                </p>
              ) : null}
            </div>
          ) : null}
          <DialogFooter>
            <Button type="submit" disabled={busy || !identifier.trim()}>
              {busy ? <Spinner data-icon="inline-start" /> : null}
              导入
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
