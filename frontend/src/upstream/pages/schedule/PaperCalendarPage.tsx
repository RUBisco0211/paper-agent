import { useQuery } from "@tanstack/react-query"
import { CalendarDays } from "lucide-react"
import { useState } from "react"

import { useApi } from "@/lib/api/provider"
import { Sidebar, SidebarContent, SidebarGroup, SidebarGroupContent, SidebarHeader, SidebarProvider } from "@upstream/components/ui/sidebar"
import { CalendarTabPage } from "./calendar-tab-page"

export function PaperCalendarPage() {
  const { api } = useApi()
  const [currentDate, setCurrentDate] = useState(new Date())
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

  return <SidebarProvider className="min-h-0 flex-1">
    <div className="flex h-full w-full">
      <Sidebar collapsible="none" className="border-r">
        <SidebarHeader className="px-4 py-5 font-semibold">日历</SidebarHeader>
        <SidebarContent>
          {projects.isPending && <p className="px-4 text-sm text-muted-foreground">加载中…</p>}
          {projects.isError && <p role="alert" className="px-4 text-sm text-destructive">无法读取项目</p>}
          {projects.isSuccess && projects.data.length === 0 && <p className="px-4 text-sm text-muted-foreground">暂无项目</p>}
          {projects.data?.map((project) => <SidebarGroup key={project.id}>
            <SidebarGroupContent>
              <div className="flex items-center gap-2 px-2 py-1.5 text-sm font-medium"><CalendarDays className="size-4" />{project.name}</div>
              <p className="px-8 py-1 text-xs text-muted-foreground">暂无定时任务</p>
            </SidebarGroupContent>
          </SidebarGroup>)}
        </SidebarContent>
      </Sidebar>
      <main className="min-w-0 flex-1 overflow-hidden bg-background">
        <CalendarTabPage events={[]} onEventClick={() => {}} currentDate={currentDate} onMonthChange={setCurrentDate} />
      </main>
    </div>
  </SidebarProvider>
}
