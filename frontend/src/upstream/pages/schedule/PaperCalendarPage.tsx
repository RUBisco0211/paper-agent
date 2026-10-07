import { useQuery } from "@tanstack/react-query"
import { CronExpressionParser } from "cron-parser"
import { Clock3, Plus } from "lucide-react"
import { useMemo, useState } from "react"

import { useApi } from "@/lib/api/provider"
import { availableChatModels } from "@/lib/agent-sessions"
import { createProjectSchedule, deleteProjectSchedule, listProjectSchedules } from "@/lib/project-schedules"
import { agentApi } from "@upstream/api/agent"
import type { ScheduleEvent } from "./event"
import { Button } from "@upstream/components/ui/button"
import { Sidebar, SidebarContent, SidebarGroup, SidebarGroupContent, SidebarHeader, SidebarProvider } from "@upstream/components/ui/sidebar"
import { CalendarTabPage } from "./calendar-tab-page"
import { ProjectScheduleDetail } from "./ProjectScheduleDetail"
import { ProjectScheduleDialog, type ScheduleDraft } from "./ProjectScheduleDialog"

function monthEvents(tasks: Awaited<ReturnType<typeof listProjectSchedules>>, currentDate: Date): ScheduleEvent[] {
  const start = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1)
  const end = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0, 23, 59, 59)
  return tasks.flatMap(({ schedule }) => {
    if (!schedule.data.enabled) return []
    const events: ScheduleEvent[] = []
    try {
      const interval = CronExpressionParser.parse(schedule.data.cron_expression, {
        currentDate: start, endDate: end, tz: schedule.data.timezone,
      })
      while (interval.hasNext() && events.length < 64) {
        const date = interval.next().toDate()
        if (date < new Date(schedule.data.started_at)) continue
        events.push({
          id: `${schedule.id}:${date.getTime()}`,
          title: schedule.data.name,
          date: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`,
          time: `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`,
          content: schedule.data.description,
        })
      }
    } catch {
      return []
    }
    return events
  })
}

export function PaperCalendarPage() {
  const { api } = useApi()
  const [currentDate, setCurrentDate] = useState(new Date())
  const [createOpen, setCreateOpen] = useState(false)
  const [createProjectId, setCreateProjectId] = useState<string | null>(null)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const projects = useQuery({
    queryKey: ["calendar-projects"],
    queryFn: async () => {
      const items: Array<{ id: string; name: string }> = []
      let total = 0
      do {
        const page = await api.projects.list({ limit: 100, offset: items.length })
        items.push(...page.items)
        total = page.total
        if (page.items.length === 0) break
      } while (items.length < total)
      return items
    },
  })
  const tasks = useQuery({
    queryKey: ["project-schedules"],
    queryFn: () => listProjectSchedules(api),
  })
  const models = useQuery({
    queryKey: ["available-chat-models"],
    queryFn: () => availableChatModels(api),
    enabled: createOpen,
  })
  const events = useMemo(() => monthEvents(tasks.data ?? [], currentDate), [tasks.data, currentDate])
  const selectedTask = tasks.data?.find((task) => task.schedule.id === selectedTaskId) ?? null
  const selectedProjectId = createProjectId ?? projects.data?.[0]?.id ?? ""

  async function create(draft: ScheduleDraft) {
    if (!selectedProjectId) throw new Error("请先选择项目")
    const listed = await agentApi.list()
    const agentId = listed.agents[0]?.id ?? (await agentApi.create({ name: "文献助手" })).agent_id
    const scheduleId = await createProjectSchedule(api, {
      projectId: selectedProjectId,
      agentId,
      ...draft,
    })
    await tasks.refetch()
    setSelectedTaskId(scheduleId)
  }

  async function remove(scheduleId: string) {
    await deleteProjectSchedule(api, scheduleId)
    setSelectedTaskId(null)
    await tasks.refetch()
  }

  return <SidebarProvider className="min-h-0 flex-1">
    <div className="flex h-full w-full">
      <Sidebar collapsible="none" className="border-r">
        <SidebarHeader className="px-4 py-5 font-semibold">定时任务</SidebarHeader>
        <SidebarContent>
          {projects.isPending && <p className="px-4 text-sm text-muted-foreground">加载中…</p>}
          {projects.isError && <p role="alert" className="px-4 text-sm text-destructive">无法读取项目</p>}
          {tasks.isError && <p role="alert" className="px-4 text-sm text-destructive">无法读取定时任务</p>}
          {projects.isSuccess && projects.data.length === 0 && <p className="px-4 text-sm text-muted-foreground">暂无项目</p>}
          {projects.data?.map((project) => <SidebarGroup key={project.id}>
            <SidebarGroupContent>
              <div className="flex items-center gap-2 px-2 py-1.5 text-sm font-medium"><Clock3 className="size-4" /><span className="min-w-0 flex-1 truncate">{project.name}</span></div>
              {tasks.data?.filter((task) => task.projectId === project.id).map((task) => <button key={task.schedule.id} type="button" className="block w-full truncate px-8 py-1 text-left text-sm hover:bg-accent" onClick={() => setSelectedTaskId(task.schedule.id)}>{task.schedule.data.name}{task.schedule.data.enabled ? "" : " · 已暂停"}</button>)}
              {!tasks.data?.some((task) => task.projectId === project.id) && <p className="px-8 py-1 text-xs text-muted-foreground">暂无定时任务</p>}
            </SidebarGroupContent>
          </SidebarGroup>)}
        </SidebarContent>
      </Sidebar>
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden bg-background">
        <div className="flex justify-end border-b px-4 py-3"><Button onClick={() => setCreateOpen(true)}><Plus className="size-4" />新建定时任务</Button></div>
        <div className="min-h-0 flex-1"><CalendarTabPage events={events} onEventClick={(event) => setSelectedTaskId(event.id.split(":")[0])} currentDate={currentDate} onMonthChange={setCurrentDate} /></div>
      </main>
    </div>
    <ProjectScheduleDialog projects={projects.data ?? []} projectId={selectedProjectId} onProjectChange={setCreateProjectId} models={models.data ?? []} open={createOpen} onOpenChange={(open) => { setCreateOpen(open); if (!open) setCreateProjectId(null) }} onCreate={create} />
    <ProjectScheduleDetail task={selectedTask} onClose={() => setSelectedTaskId(null)} onDelete={remove} />
  </SidebarProvider>
}
