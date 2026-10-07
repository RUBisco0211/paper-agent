import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Pause, Play, RefreshCw, Trash2, X } from "lucide-react"
import { useState } from "react"
import { useNavigate } from "react-router-dom"

import type { ProjectSchedule } from "@/lib/project-schedules"
import { scheduleApi } from "@upstream/api/schedule"
import { Button } from "@upstream/components/ui/button"
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@upstream/components/ui/sheet"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@upstream/components/ui/tooltip"
import { parseCronExpression } from "./schedule-utils"
import { describeScheduleFrequency } from "./schedule-frequency"

function formatRunTime(value: string, timezone: string): string {
  // AgentScope stores UTC without an offset; Date would otherwise read it as local time.
  const timestamp = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return "时间未知"
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: timezone,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(date)
}

export function ProjectScheduleDetail({
  task,
  onClose,
  onDelete,
}: {
  task: ProjectSchedule | null
  onClose: () => void
  onDelete: (scheduleId: string) => Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const scheduleId = task?.schedule.id ?? ""
  const runs = useQuery({
    queryKey: ["schedule-runs", scheduleId],
    queryFn: () => scheduleApi.listSessions(scheduleId),
    enabled: Boolean(scheduleId),
  })

  if (!task) return null
  const parsed = parseCronExpression(task.schedule.data.cron_expression, task.schedule.data.started_at)
  const cadence = describeScheduleFrequency(task.schedule.data.cron_expression)

  async function changeEnabled() {
    if (!task) return
    setBusy(true)
    setError("")
    try {
      await scheduleApi.update(task.schedule.id, { enabled: !task.schedule.data.enabled })
      await queryClient.invalidateQueries({ queryKey: ["project-schedules"] })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "更新失败，请重试")
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!task) return
    if (!window.confirm("删除定时任务及全部运行记录？此操作不可撤销。")) return
    setBusy(true)
    setError("")
    try {
      await onDelete(task.schedule.id)
      onClose()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "删除失败，请重试")
    } finally {
      setBusy(false)
    }
  }

  return <>
    <Sheet open={Boolean(task)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" showCloseButton={false} className="overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-4xl">
        <SheetHeader className="flex-row items-start justify-between gap-4 border-b">
          <div className="min-w-0 flex-1">
            <SheetTitle className="truncate text-xl">{task.schedule.data.name}</SheetTitle>
            <SheetDescription>{cadence} {parsed.time} · {task.schedule.data.timezone}</SheetDescription>
          </div>
          <TooltipProvider>
            <div className="flex shrink-0 items-center gap-1">
              <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="icon-sm" aria-label={task.schedule.data.enabled ? "暂停任务" : "启用任务"} disabled={busy} onClick={() => void changeEnabled()}>{task.schedule.data.enabled ? <Pause className="size-4" /> : <Play className="size-4" />}</Button></TooltipTrigger><TooltipContent>{task.schedule.data.enabled ? "暂停任务" : "启用任务"}</TooltipContent></Tooltip>
              <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="刷新结果" disabled={runs.isFetching} onClick={() => void runs.refetch()}><RefreshCw className="size-4" /></Button></TooltipTrigger><TooltipContent>刷新结果</TooltipContent></Tooltip>
              <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="删除任务" className="text-destructive hover:text-destructive" disabled={busy} onClick={() => void remove()}><Trash2 className="size-4" /></Button></TooltipTrigger><TooltipContent>删除任务</TooltipContent></Tooltip>
              <Tooltip><TooltipTrigger asChild><SheetClose asChild><Button variant="ghost" size="icon-sm" aria-label="关闭"><X className="size-4" /></Button></SheetClose></TooltipTrigger><TooltipContent>关闭</TooltipContent></Tooltip>
            </div>
          </TooltipProvider>
        </SheetHeader>
        {error && <p role="alert" className="px-4 text-sm text-destructive">{error}</p>}
        <p className="mx-4 whitespace-pre-wrap border-l-2 pl-3 text-sm">{task.schedule.data.description}</p>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-6">
          <h3 className="mb-2 text-sm font-medium">运行记录</h3>
          {runs.isPending && <p className="text-sm text-muted-foreground">加载中…</p>}
          {runs.isError && <p role="alert" className="text-sm text-destructive">无法读取运行记录</p>}
          {runs.data?.sessions.length === 0 && <p className="text-sm text-muted-foreground">尚无运行记录</p>}
          <div className="flex flex-col gap-1">
            {runs.data?.sessions.map((run) => <Button key={run.id} type="button" variant="ghost" className="w-full justify-start text-left" onClick={() => { onClose(); navigate(`/scheduled/${task.schedule.id}/runs/${run.id}`) }}>{formatRunTime(run.created_at, task.schedule.data.timezone)}</Button>)}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  </>
}
