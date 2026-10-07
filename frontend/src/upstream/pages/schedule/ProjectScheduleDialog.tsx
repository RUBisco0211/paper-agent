import { useEffect, useState } from "react"

import type { ChatModelConfig } from "@upstream/api/types"
import { Button } from "@upstream/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@upstream/components/ui/dialog"
import { Input } from "@upstream/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@upstream/components/ui/select"
import { Textarea } from "@upstream/components/ui/textarea"

export interface ScheduleDraft {
  name: string
  prompt: string
  cronExpression: string
  timezone: string
  model: ChatModelConfig
}

export function ProjectScheduleDialog({
  projects,
  projectId,
  onProjectChange,
  models,
  open,
  onOpenChange,
  onCreate,
}: {
  projects: Array<{ id: string; name: string }>
  projectId: string
  onProjectChange: (projectId: string) => void
  models: ChatModelConfig[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreate: (draft: ScheduleDraft) => Promise<void>
}) {
  const [name, setName] = useState("")
  const [prompt, setPrompt] = useState("")
  const [frequency, setFrequency] = useState("daily")
  const [weekday, setWeekday] = useState("1")
  const [time, setTime] = useState("09:00")
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC")
  const [modelIndex, setModelIndex] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (open) setError("")
  }, [open])

  async function submit() {
    const model = models[modelIndex]
    const [hour, minute] = time.split(":").map(Number)
    if (!name.trim() || !prompt.trim() || !model || !Number.isInteger(hour) || !Number.isInteger(minute)) return
    const cronExpression = frequency === "weekly"
      ? `${minute} ${hour} * * ${weekday}`
      : `${minute} ${hour} * * *`
    setBusy(true)
    setError("")
    try {
      await onCreate({ name: name.trim(), prompt: prompt.trim(), cronExpression, timezone, model })
      onOpenChange(false)
      setName("")
      setPrompt("")
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "创建失败，请重试")
    } finally {
      setBusy(false)
    }
  }

  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="sm:max-w-lg">
      <DialogHeader><DialogTitle>新建定时任务</DialogTitle></DialogHeader>
      <div className="grid gap-4">
        <label className="grid gap-1 text-sm">项目<Select value={projectId || undefined} onValueChange={onProjectChange}><SelectTrigger><SelectValue placeholder="选择项目" /></SelectTrigger><SelectContent>{projects.map((project) => <SelectItem key={project.id} value={project.id}>{project.name}</SelectItem>)}</SelectContent></Select></label>
        {projects.length === 0 && <p className="text-sm text-muted-foreground">请先创建项目</p>}
        <label className="grid gap-1 text-sm">名称<Input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} /></label>
        <label className="grid gap-1 text-sm">任务提示词<Textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} className="min-h-28" /></label>
        <div className="grid grid-cols-2 gap-3">
          <label className="grid gap-1 text-sm">频率<Select value={frequency} onValueChange={setFrequency}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="daily">每天</SelectItem><SelectItem value="weekly">每周</SelectItem></SelectContent></Select></label>
          <label className="grid gap-1 text-sm">时间<Input type="time" value={time} onChange={(event) => setTime(event.target.value)} /></label>
        </div>
        {frequency === "weekly" && <label className="grid gap-1 text-sm">星期<Select value={weekday} onValueChange={setWeekday}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["日", "一", "二", "三", "四", "五", "六"].map((day, index) => <SelectItem key={index} value={String(index)}>周{day}</SelectItem>)}</SelectContent></Select></label>}
        <label className="grid gap-1 text-sm">时区<Input value={timezone} onChange={(event) => setTimezone(event.target.value)} /></label>
        <label className="grid gap-1 text-sm">模型<Select value={String(modelIndex)} onValueChange={(value) => setModelIndex(Number(value))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{models.map((model, index) => <SelectItem key={`${model.credential_id}:${model.model}`} value={String(index)}>{model.model}</SelectItem>)}</SelectContent></Select></label>
        {models.length === 0 && <p className="text-sm text-muted-foreground">请先在模型设置中保存凭据</p>}
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      </div>
      <DialogFooter><Button disabled={busy || !projectId || !name.trim() || !prompt.trim() || !models.length || !timezone.trim()} onClick={() => void submit()}>创建任务</Button></DialogFooter>
    </DialogContent>
  </Dialog>
}
