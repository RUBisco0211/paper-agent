import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import type { ProjectSchedule } from "@/lib/project-schedules"
import { scheduleApi } from "@upstream/api/schedule"
import { sessionApi } from "@upstream/api/session"
import { ASMessageBubble } from "@upstream/components/chat/ASMessageBubble"
import { CitationProvider } from "@upstream/components/chat/citation-context"
import { Button } from "@upstream/components/ui/button"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@upstream/components/ui/sheet"
import { BoundCitationSheet } from "@upstream/pages/chat/BoundCitationSheet"
import { parseCronExpression } from "./schedule-utils"
import { describeScheduleFrequency } from "./schedule-frequency"

export function ProjectScheduleDetail({
  task,
  onClose,
  onDelete,
}: {
  task: ProjectSchedule | null
  onClose: () => void
  onDelete: (scheduleId: string) => Promise<void>
}) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [citationId, setCitationId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const queryClient = useQueryClient()
  const scheduleId = task?.schedule.id ?? ""
  const runs = useQuery({
    queryKey: ["schedule-runs", scheduleId],
    queryFn: () => scheduleApi.listSessions(scheduleId),
    enabled: Boolean(scheduleId),
  })
  const runId = selectedRunId ?? runs.data?.sessions[0]?.id ?? null
  const messages = useQuery({
    queryKey: ["schedule-run-messages", runId],
    queryFn: () => sessionApi.messages(runId!, task!.schedule.agent_id),
    enabled: Boolean(runId && task),
  })

  useEffect(() => {
    setSelectedRunId(null)
    setCitationId(null)
    setError("")
  }, [scheduleId])

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
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-3xl">
        <SheetHeader>
          <SheetTitle>{task.schedule.data.name}</SheetTitle>
          <SheetDescription>{cadence} {parsed.time} · {task.schedule.data.timezone}</SheetDescription>
        </SheetHeader>
        <div className="flex flex-wrap gap-2 px-4">
          <Button variant="outline" size="sm" disabled={busy} onClick={() => void changeEnabled()}>{task.schedule.data.enabled ? "暂停" : "启用"}</Button>
          <Button variant="outline" size="sm" onClick={() => void runs.refetch()}>刷新结果</Button>
          <Button variant="destructive" size="sm" disabled={busy} onClick={() => void remove()}>删除任务</Button>
        </div>
        {error && <p role="alert" className="px-4 text-sm text-destructive">{error}</p>}
        <p className="mx-4 whitespace-pre-wrap border-l-2 pl-3 text-sm">{task.schedule.data.description}</p>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-6">
          <h3 className="mb-2 text-sm font-medium">运行记录</h3>
          {runs.isPending && <p className="text-sm text-muted-foreground">加载中…</p>}
          {runs.isError && <p role="alert" className="text-sm text-destructive">无法读取运行记录</p>}
          {runs.data?.sessions.length === 0 && <p className="text-sm text-muted-foreground">尚无运行记录</p>}
          <div className="mb-4 flex flex-wrap gap-2">
            {runs.data?.sessions.map((run) => <Button key={run.id} size="sm" variant={run.id === runId ? "secondary" : "outline"} onClick={() => setSelectedRunId(run.id)}>{new Date(run.created_at).toLocaleString()}</Button>)}
          </div>
          {messages.isPending && runId && <p className="text-sm text-muted-foreground">加载结果中…</p>}
          {messages.isError && <p role="alert" className="text-sm text-destructive">无法读取此次结果</p>}
          {messages.data && <CitationProvider onOpen={setCitationId}><div className="space-y-4">{messages.data.messages.filter((message) => message.role === "assistant").map((message) => <ASMessageBubble key={message.id} message={message} onUserConfirm={() => setError("定时任务无法等待人工确认")} />)}</div></CitationProvider>}
        </div>
      </SheetContent>
    </Sheet>
    {runId && <BoundCitationSheet sessionId={runId} citationId={citationId} onOpenChange={(open) => !open && setCitationId(null)} />}
  </>
}
