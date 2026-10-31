import { useEffect, useRef, useState } from "react"

import type { ChatModelConfig } from "@/types/agent"
import type { ReviewedSchedule, ScheduleDraft, ScheduleFrequency } from "@/types/schedule"
import { useAuth } from "@/components/providers/AuthProvider"
import { TimezoneSelect } from "@/components/settings/TimezoneSelect"
import { Button } from "@/components/ui/Button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/Dialog"
import { Input } from "@/components/ui/Input"
import { Checkbox } from "@/components/ui/Checkbox"
import { Field, FieldDescription, FieldLabel } from "@/components/ui/Field"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/Select"
import { Textarea } from "@/components/ui/Textarea"
import { cronForFrequency, DAY_CODES } from "./scheduleFrequency"

function frequencyFor(days: string[]): ScheduleFrequency {
  const sorted = [...new Set(days)].sort().join(",")
  if (days.length === 7) return "daily"
  if (sorted === "fri,mon,thu,tue,wed") return "weekdays"
  if (sorted === "sat,sun") return "weekends"
  return days.length === 1 ? "weekly" : "custom"
}

export function ProjectScheduleDialog({
  projects,
  projectId,
  onProjectChange,
  models,
  open,
  onOpenChange,
  onCreate,
  review,
  onReview,
}: {
  projects: Array<{ id: string; name: string }>
  projectId: string
  onProjectChange: (projectId: string) => void
  models: ChatModelConfig[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreate?: (draft: ScheduleDraft) => Promise<void>
  review?: ReviewedSchedule
  onReview?: (draft: ReviewedSchedule) => Promise<void>
}) {
  const { preferences } = useAuth()
  const [name, setName] = useState("")
  const [prompt, setPrompt] = useState("")
  const [frequency, setFrequency] = useState<ScheduleFrequency>("daily")
  const [weekday, setWeekday] = useState(1)
  const [customDays, setCustomDays] = useState<number[]>([])
  const [time, setTime] = useState("09:00")
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC")
  const [modelIndex, setModelIndex] = useState(0)
  const [notifyEmail, setNotifyEmail] = useState(false)
  const [busy, setBusy] = useState(false)
  const submitting = useRef(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (!open) return
    setError("")
    setNotifyEmail(review?.notify_email ?? preferences?.notify_email_default ?? false)
    if (!review) return
    const days = review.weekdays.map((day) => DAY_CODES.indexOf(day)).filter((day) => day >= 0)
    setName(review.name)
    setPrompt(review.prompt)
    setTime(review.time)
    setFrequency(frequencyFor(review.weekdays))
    setWeekday(days[0] ?? 1)
    setCustomDays(days)
  }, [open, review])

  async function submit() {
    if (submitting.current) return
    const model = models[modelIndex]
    if (!name.trim() || !prompt.trim() || (!review && !model)) return
    submitting.current = true
    setBusy(true)
    setError("")
    try {
      const cronExpression = cronForFrequency(frequency, time, frequency === "weekly" ? [weekday] : customDays)
      if (review) {
        const selectedDays = frequency === "daily" ? [0, 1, 2, 3, 4, 5, 6]
          : frequency === "weekdays" ? [1, 2, 3, 4, 5]
          : frequency === "weekends" ? [0, 6]
          : frequency === "weekly" ? [weekday] : customDays
        if (!onReview) return
        await onReview({
          name: name.trim(), prompt: prompt.trim(), time,
          weekdays: selectedDays.map((day) => DAY_CODES[day]),
          notify_email: notifyEmail,
        })
      } else {
        if (!model || !onCreate) return
        await onCreate({ name: name.trim(), prompt: prompt.trim(), cronExpression, timezone, model, notify_email: notifyEmail })
      }
      onOpenChange(false)
      setName("")
      setPrompt("")
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "创建失败，请重试")
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="sm:max-w-lg">
      <DialogHeader><DialogTitle>新建定时任务</DialogTitle></DialogHeader>
      <div className="grid gap-4">
        {review ? <div className="grid gap-1 text-sm"><span>范围</span><span>{projects.find((project) => project.id === projectId)?.name ?? "全局"}</span></div>
          : <label className="grid gap-1 text-sm">范围<Select value={projectId || "__global__"} onValueChange={(value) => onProjectChange(value === "__global__" ? "" : value)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="__global__">全局</SelectItem>{projects.map((project) => <SelectItem key={project.id} value={project.id}>{project.name}</SelectItem>)}</SelectContent></Select></label>}
        <label className="grid gap-1 text-sm">名称<Input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} /></label>
        <label className="grid gap-1 text-sm">任务提示词<Textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} className="min-h-28" /></label>
        <div className="grid grid-cols-2 gap-3">
          <label className="grid gap-1 text-sm">频率<Select value={frequency} onValueChange={(value) => setFrequency(value as ScheduleFrequency)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="daily">每天</SelectItem><SelectItem value="weekly">每周</SelectItem><SelectItem value="weekdays">工作日</SelectItem><SelectItem value="weekends">周末</SelectItem><SelectItem value="custom">自定义</SelectItem></SelectContent></Select></label>
          <label className="grid gap-1 text-sm">时间<Input type="time" value={time} onChange={(event) => setTime(event.target.value)} /></label>
        </div>
        {frequency === "weekly" && <label className="grid gap-1 text-sm">星期<Select value={String(weekday)} onValueChange={(value) => setWeekday(Number(value))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["日", "一", "二", "三", "四", "五", "六"].map((day, index) => <SelectItem key={index} value={String(index)}>周{day}</SelectItem>)}</SelectContent></Select></label>}
        {frequency === "custom" && <div className="grid gap-2 text-sm"><span>星期</span><div className="flex flex-wrap gap-2">{["日", "一", "二", "三", "四", "五", "六"].map((day, index) => <Button key={index} type="button" size="sm" variant={customDays.includes(index) ? "default" : "outline"} aria-pressed={customDays.includes(index)} onClick={() => setCustomDays((current) => current.includes(index) ? current.filter((item) => item !== index) : [...current, index])}>周{day}</Button>)}</div></div>}
        {!review && <label className="grid gap-1 text-sm">时区<TimezoneSelect value={timezone} onChange={setTimezone} /></label>}
        {!review && <label className="grid gap-1 text-sm">模型<Select value={String(modelIndex)} onValueChange={(value) => setModelIndex(Number(value))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{models.map((model, index) => <SelectItem key={`${model.credential_id}:${model.model}`} value={String(index)}>{model.model}</SelectItem>)}</SelectContent></Select></label>}
        {!review && models.length === 0 && <p className="text-sm text-muted-foreground">请先在模型设置中保存凭据</p>}
        <Field orientation="horizontal" data-disabled={busy}>
          <Checkbox id="schedule-notify-email" checked={notifyEmail} onCheckedChange={(checked) => setNotifyEmail(checked === true)} disabled={busy} />
          <div className="flex flex-col gap-1"><FieldLabel htmlFor="schedule-notify-email">邮件通知</FieldLabel><FieldDescription>发送到当前账号邮箱</FieldDescription></div>
        </Field>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      </div>
      <DialogFooter><Button disabled={busy || (frequency === "custom" && customDays.length === 0) || !name.trim() || !prompt.trim() || (!review && (!models.length || !timezone.trim()))} onClick={() => void submit()}>{review ? "确认创建" : "创建任务"}</Button></DialogFooter>
    </DialogContent>
  </Dialog>
}
