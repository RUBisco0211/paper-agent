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
import { Spinner } from "@/components/ui/Spinner"
import type { DownloadRead } from "@/types/business"
import { useApi } from "@/components/providers/ApiProvider"
import { describeError, notifySuccess } from "@/lib/errors"

/** DOI/arXiv import: fetch the source file, then parse it. */
export function ImportDialog({
  onImported,
  trigger,
}: {
  onImported?: (result: DownloadRead) => void
  trigger?: React.ReactNode
}) {
  const { api } = useApi()
  const [open, setOpen] = useState(false)
  const [identifier, setIdentifier] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<DownloadRead | null>(null)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      // The request only records the work; the queue carries it from here.
      const started = await api.imports.start(identifier.trim())
      setResult(started)
      notifySuccess("已提交，可在入库队列查看进度")
      onImported?.(started)
    } catch (cause) {
      setError(describeError(cause))
    } finally {
      setBusy(false)
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
          {error ? <p className="text-destructive text-sm">{error}</p> : null}
          {result ? (
            <div className="bg-muted/50 rounded-md p-3 text-sm">
              <p className="font-medium">已提交获取原文</p>
              <p className="text-muted-foreground mt-1">
                处理完成后会出现在文献库，进度见
                <Link className="underline" to="/library" onClick={() => handleOpenChange(false)}>
                  入库队列
                </Link>
              </p>
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
