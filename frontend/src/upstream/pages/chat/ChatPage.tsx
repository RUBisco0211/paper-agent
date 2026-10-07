import { useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { Outlet, useLocation, useNavigate } from "react-router-dom"

import { useApi } from "@/lib/api/provider"
import { listBoundSessions } from "@/lib/agent-sessions"
import { SidebarProvider } from "@upstream/components/ui/sidebar"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@upstream/components/ui/resizable"
import { ChatSidebar } from "./ChatSidebar"
import { ProjectPapersPanel } from "./ProjectPapersPanel"
import { chatPath, mostRecentSession } from "./chat-view"

export function ChatPage() {
  const { api } = useApi()
  const navigate = useNavigate()
  const location = useLocation()
  const [papersOpen, setPapersOpen] = useState(true)
  const sessions = useQuery({ queryKey: ["bound-sessions"], queryFn: () => listBoundSessions(api) })

  useEffect(() => {
    if (location.pathname !== "/chat" || !sessions.isSuccess) return
    const recent = mostRecentSession(sessions.data)
    if (recent) navigate(chatPath(recent), { replace: true })
  }, [location.pathname, sessions.isSuccess, sessions.data, navigate])

  const projectRouteId = location.pathname.startsWith("/chat/project/") ? location.pathname.split("/")[3] : null
  const activeSession = sessions.data?.find((item) => chatPath(item) === location.pathname)
  const projectId = projectRouteId ?? activeSession?.binding.project_id ?? null

  useEffect(() => {
    if (projectRouteId) setPapersOpen(true)
  }, [projectRouteId])

  const main = <div className="h-full min-w-0 overflow-hidden bg-background">
    {location.pathname === "/chat" ? <div className="flex h-full items-center justify-center text-muted-foreground">{sessions.isPending ? "加载中…" : "新建会话后开始提问"}</div> : <Outlet context={{ papersOpen, togglePapers: () => setPapersOpen((open) => !open), projectId }} />}
  </div>

  return <SidebarProvider className="min-h-0 flex-1">
    <div className="flex h-full w-full">
      <ChatSidebar />
      <ResizablePanelGroup orientation="horizontal" className="min-w-0 flex-1">
        <ResizablePanel minSize="24rem">{main}</ResizablePanel>
        {projectId && papersOpen && <>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize="24rem" minSize="18rem" maxSize="50rem"><ProjectPapersPanel key={projectId} projectId={projectId} /></ResizablePanel>
        </>}
      </ResizablePanelGroup>
    </div>
  </SidebarProvider>
}
