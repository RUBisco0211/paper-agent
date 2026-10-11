import { useQuery } from "@tanstack/react-query"
import { CronExpressionParser } from "cron-parser"
import { ChevronDown, MoreHorizontal, Plus } from "lucide-react"
import { useMemo, useState } from "react"
import { useParams } from "react-router-dom"

import { useApi } from "@/lib/api/provider"
import { availableChatModels, sameSessionId } from "@/lib/agent-sessions"
import { createProjectSchedule, deleteProjectSchedule, listProjectSchedules, type ProjectSchedule } from "@/lib/project-schedules"
import { agentApi } from "@upstream/api/agent"
import { scheduleApi } from "@upstream/api/schedule"
import { Button } from "@upstream/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@upstream/components/ui/collapsible"
import { PaperChatPage } from "@upstream/pages/chat/PaperChatPage"
import type { ScheduleEvent } from "./event"
import { Sidebar, SidebarContent, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader, SidebarMenu, SidebarMenuAction, SidebarMenuButton, SidebarMenuItem, SidebarProvider } from "@upstream/components/ui/sidebar"
import { CalendarTabPage } from "./calendar-tab-page"
import { ProjectScheduleDetail } from "./ProjectScheduleDetail"
import { ProjectScheduleDialog, type ScheduleDraft } from "./ProjectScheduleDialog"
import { calendarCronExpression } from "./schedule-frequency"

function monthEvents(tasks: Awaited<ReturnType<typeof listProjectSchedules>>, currentDate: Date): ScheduleEvent[] {
  const start = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1)
  const end = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0, 23, 59, 59)
  return tasks.flatMap(({ schedule }) => {
    if (!schedule.data.enabled) return []
    const events: ScheduleEvent[] = []
    try {
      const interval = CronExpressionParser.parse(calendarCronExpression(schedule.data.cron_expression), {
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

function TaskRows({ tasks, activeTaskId, onSelect }: { tasks: ProjectSchedule[]; activeTaskId: string | null; onSelect: (scheduleId: string) => void }) {
  return tasks.map((task) => <SidebarMenuItem key={task.schedule.id}>
    <SidebarMenuButton type="button" isActive={activeTaskId === task.schedule.id} onClick={() => onSelect(task.schedule.id)}>
      <span className="truncate">{task.schedule.data.name}{task.schedule.data.enabled ? "" : " · 已暂停"}</span>
    </SidebarMenuButton>
    <SidebarMenuAction type="button" showOnHover aria-label={`${task.schedule.data.name}详情`} onClick={() => onSelect(task.schedule.id)}><MoreHorizontal /></SidebarMenuAction>
  </SidebarMenuItem>)
}

export function PaperCalendarPage() {
  const { scheduleId, sessionId } = useParams()
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
  const routeTask = tasks.data?.find((task) => task.schedule.id === scheduleId)
  const routeRuns = useQuery({
    queryKey: ["schedule-runs", scheduleId],
    queryFn: () => scheduleApi.listSessions(scheduleId!),
    enabled: Boolean(scheduleId && routeTask),
  })
  const routeRun = routeRuns.data?.sessions.find((run) => sameSessionId(run.id, sessionId ?? "") && run.source_schedule_id === scheduleId)
  const routeProject = projects.data?.find((project) => project.id === routeTask?.projectId)
  const models = useQuery({
    queryKey: ["available-chat-models"],
    queryFn: () => availableChatModels(api),
    enabled: createOpen,
  })
  const events = useMemo(() => monthEvents(tasks.data ?? [], currentDate), [tasks.data, currentDate])
  const orderedTasks = useMemo(() => [...(tasks.data ?? [])].sort((a, b) => (b.schedule.created_at ?? "").localeCompare(a.schedule.created_at ?? "")), [tasks.data])
  const selectedTask = tasks.data?.find((task) => task.schedule.id === selectedTaskId) ?? null
  const selectedProjectId = createProjectId ?? ""
  const activeTaskId = selectedTaskId ?? scheduleId ?? null

  function openCreate(projectId: string | null) {
    setCreateProjectId(projectId)
    setCreateOpen(true)
  }

  async function create(draft: ScheduleDraft) {
    const listed = await agentApi.list()
    const agentId = listed.agents[0]?.id ?? (await agentApi.create({ name: "文献助手" })).agent_id
    const scheduleId = await createProjectSchedule(api, {
      projectId: selectedProjectId || null,
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
        <SidebarHeader className="h-12 justify-center px-4 font-semibold tracking-tight">定时任务</SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel className="flex items-center justify-between">全局
              <button type="button" aria-label="新建全局定时任务" onClick={() => openCreate(null)}><Plus className="size-4" /></button>
            </SidebarGroupLabel>
            <SidebarGroupContent><SidebarMenu><TaskRows tasks={orderedTasks.filter((task) => task.projectId === null)} activeTaskId={activeTaskId} onSelect={setSelectedTaskId} /></SidebarMenu></SidebarGroupContent>
          </SidebarGroup>
          {projects.isPending && <p className="px-4 text-sm text-muted-foreground">加载中…</p>}
          {projects.isError && <p role="alert" className="px-4 text-sm text-destructive">无法读取项目</p>}
          {tasks.isError && <p role="alert" className="px-4 text-sm text-destructive">无法读取定时任务</p>}
          {projects.isSuccess && projects.data.length === 0 && <p className="px-4 text-sm text-muted-foreground">暂无项目</p>}
          {projects.data?.map((project) => <Collapsible key={project.id} defaultOpen><SidebarGroup>
            <SidebarGroupLabel className="flex items-center justify-between">
              <CollapsibleTrigger className="flex min-w-0 items-center gap-1 truncate"><ChevronDown className="size-3.5" />{project.name}</CollapsibleTrigger>
              <button type="button" aria-label={`在${project.name}中新建定时任务`} onClick={() => openCreate(project.id)}><Plus className="size-4" /></button>
            </SidebarGroupLabel>
            <CollapsibleContent><SidebarGroupContent><SidebarMenu>
              <TaskRows tasks={orderedTasks.filter((task) => task.projectId === project.id)} activeTaskId={activeTaskId} onSelect={setSelectedTaskId} />
            </SidebarMenu>
              {!tasks.data?.some((task) => task.projectId === project.id) && <p className="px-2 py-1 text-xs text-muted-foreground">暂无定时任务</p>}
            </SidebarGroupContent></CollapsibleContent>
          </SidebarGroup></Collapsible>)}
        </SidebarContent>
      </Sidebar>
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden bg-background">
        {sessionId ? <>
          <div className="min-h-0 flex-1">
            {tasks.isPending || (routeTask && routeRuns.isPending) ? <p className="p-5 text-sm text-muted-foreground">加载中…</p>
              : tasks.isError || routeRuns.isError ? <p role="alert" className="p-5 text-sm text-destructive">无法读取会话</p>
              : routeRun && routeTask ? <PaperChatPage scheduledRun={routeRun} scheduledScope={routeTask.projectId ? routeProject?.name ?? "项目" : "全局"} />
              : <p role="alert" className="p-5 text-sm text-muted-foreground">会话不存在</p>}
          </div>
        </> : <>
          <div className="flex h-12 shrink-0 items-center justify-end border-b px-4"><Button onClick={() => openCreate(null)}><Plus className="size-4" />新建定时任务</Button></div>
          <div className="min-h-0 flex-1"><CalendarTabPage events={events} onEventClick={(event) => setSelectedTaskId(event.id.split(":")[0])} currentDate={currentDate} onMonthChange={setCurrentDate} /></div>
        </>}
      </main>
    </div>
    <ProjectScheduleDialog projects={projects.data ?? []} projectId={selectedProjectId} onProjectChange={setCreateProjectId} models={models.data ?? []} open={createOpen} onOpenChange={(open) => { setCreateOpen(open); if (!open) setCreateProjectId(null) }} onCreate={create} />
    {selectedTask && <ProjectScheduleDetail task={selectedTask} onClose={() => setSelectedTaskId(null)} onDelete={remove} />}
  </SidebarProvider>
}
