import { useQuery } from "@tanstack/react-query"
import { PanelLeftClose, PanelLeftOpen } from "lucide-react"
import { usePanelRef } from "react-resizable-panels"
import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { useLocation, useNavigate, useOutlet } from "react-router-dom"

import { useApi } from "@/lib/api/provider"
import { listBoundSessions } from "@/lib/agent-sessions"
import { Button } from "@upstream/components/ui/button"
import { SidebarProvider } from "@upstream/components/ui/sidebar"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@upstream/components/ui/resizable"
import { ChatSidebar } from "./ChatSidebar"
import { ChatQuoteContext, type ChatQuoteReceiver, type PaperQuoteOpener } from "./ChatQuoteContext"
import type { QuoteReference } from "@upstream/components/chat/quote-references"
import { ProjectPapersPanel } from "./ProjectPapersPanel"
import { chatPath } from "./chat-view"

export function ChatPage() {
  const { api } = useApi()
  const navigate = useNavigate()
  const location = useLocation()
  const outlet = useOutlet()
  const mainRef = useRef<HTMLDivElement>(null)
  const previousPath = useRef<string | null>(null)
  const [leftOpen, setLeftOpen] = useState(true)
  const [papersOpen, setPapersOpen] = useState(true)
  const [readingPaper, setReadingPaper] = useState(false)
  const papersPanelRef = usePanelRef()
  const listPanelWidth = useRef<number | null>(null)
  const previousPaperProject = useRef<string | null>(null)
  const quoteReceivers = useRef(new Map<string, ChatQuoteReceiver>())
  const paperOpeners = useRef(new Map<string, PaperQuoteOpener>())
  const quoteBridge = useRef({
    register: (sessionId: string, receiver: ChatQuoteReceiver) => {
      quoteReceivers.current.set(sessionId, receiver)
      return () => { if (quoteReceivers.current.get(sessionId) === receiver) quoteReceivers.current.delete(sessionId) }
    },
    add: (sessionId: string, reference: QuoteReference) => quoteReceivers.current.get(sessionId)?.(reference) ?? false,
    registerPaperOpener: (sessionId: string, opener: PaperQuoteOpener) => {
      paperOpeners.current.set(sessionId, opener)
      return () => { if (paperOpeners.current.get(sessionId) === opener) paperOpeners.current.delete(sessionId) }
    },
    openPaper: (sessionId: string, reference: Extract<QuoteReference, { kind: 'parsed_block' | 'pdf_selection' }>) => {
      const opened = paperOpeners.current.get(sessionId)?.(reference) ?? false
      if (opened) setPapersOpen(true)
      return opened
    },
  }).current
  const sessions = useQuery({ queryKey: ["bound-sessions"], queryFn: () => listBoundSessions(api) })

  useEffect(() => {
    if (!sessions.isSuccess) return
    const path = location.pathname
    if (/^\/chat\/[^/]+\/[^/]+$/.test(path) && !path.startsWith("/chat/project/") &&
        !sessions.data.some((session) => chatPath(session) === path)) {
      navigate("/chat", { replace: true })
    }
  }, [location.pathname, sessions.isSuccess, sessions.data, navigate])

  const projectRouteId = location.pathname.startsWith("/chat/project/") ? location.pathname.split("/")[3] : null
  const activeSession = sessions.data?.find((item) => chatPath(item) === location.pathname)
  const projectId = projectRouteId ?? activeSession?.binding.project_id ?? null

  useEffect(() => {
    if (projectRouteId) setPapersOpen(true)
  }, [projectRouteId])

  useEffect(() => {
    if (previousPaperProject.current !== projectId) {
      previousPaperProject.current = projectId
      listPanelWidth.current = null
      setReadingPaper(false)
      return
    }
    if (!projectId) { listPanelWidth.current = null; setReadingPaper(false); return }
    const frame = requestAnimationFrame(() => {
      const panel = papersPanelRef.current
      if (!panel) return
      if (readingPaper) {
        if (listPanelWidth.current === null) listPanelWidth.current = panel.getSize().inPixels
        panel.resize("58%")
      } else if (listPanelWidth.current !== null) {
        panel.resize(listPanelWidth.current)
        listPanelWidth.current = null
      }
    })
    return () => cancelAnimationFrame(frame)
  }, [readingPaper, projectId, papersPanelRef])

  useEffect(() => {
    if (!projectId) return
    const frame = requestAnimationFrame(() => {
      if (papersOpen) papersPanelRef.current?.expand()
      else papersPanelRef.current?.collapse()
    })
    return () => cancelAnimationFrame(frame)
  }, [papersOpen, projectId, papersPanelRef])

  useLayoutEffect(() => {
    if (previousPath.current === null) { previousPath.current = location.pathname; return }
    if (previousPath.current === location.pathname) return
    previousPath.current = location.pathname
    const node = mainRef.current
    if (!node) return
    node.classList.remove("route-page-enter")
    void node.offsetWidth
    node.classList.add("route-page-enter")
    return () => node.classList.remove("route-page-enter")
  }, [location.pathname])

  const title = location.pathname === "/chat/new" ? "新会话"
    : activeSession?.session.session.config.name || "对话"
  const main = <div ref={mainRef} className="h-full min-w-0 overflow-hidden bg-background">
    {outlet}
  </div>

  return <ChatQuoteContext.Provider value={quoteBridge}><SidebarProvider className="min-h-0 flex-1">
    <div className="flex h-full min-h-0 w-full flex-col">
      <header data-slot="app-toolbar" aria-label="会话工具栏" className="flex h-(--app-toolbar-height) shrink-0 items-center gap-3 border-b bg-[var(--app-rail-background)] px-3 text-foreground">
        <Button variant="ghost" size="icon-sm" aria-label={leftOpen ? "收起会话侧栏" : "展开会话侧栏"} title={leftOpen ? "收起会话侧栏" : "展开会话侧栏"} onClick={() => setLeftOpen((open) => !open)}>{leftOpen ? <PanelLeftClose /> : <PanelLeftOpen />}</Button>
        <span className="min-w-0 truncate text-sm font-medium">{title}</span>
      </header>
      <div className="flex min-h-0 flex-1">
        <div aria-hidden={!leftOpen} inert={!leftOpen} className={`h-full shrink-0 overflow-hidden transition-[width,opacity] duration-(--motion-duration-normal) ease-(--motion-ease-standard) motion-reduce:transition-none ${leftOpen ? "w-(--chat-sidebar-width) opacity-100" : "w-0 opacity-0"}`}>
          <ChatSidebar currentProjectId={projectId} papersOpen={papersOpen} onTogglePapers={() => setPapersOpen((open) => !open)} />
        </div>
        <ResizablePanelGroup orientation="horizontal" className="min-w-0 flex-1">
          <ResizablePanel minSize="24rem">{main}</ResizablePanel>
          {projectId && <>
            <ResizableHandle withHandle className={papersOpen ? "" : "pointer-events-none opacity-0"} />
            <ResizablePanel data-animated-sidebar panelRef={papersPanelRef} collapsible collapsedSize={0} defaultSize="24rem" minSize="18rem" maxSize="75%"><ProjectPapersPanel key={projectId} projectId={projectId} sessionId={activeSession?.session.session.id ?? null} onReadingChange={setReadingPaper} /></ResizablePanel>
          </>}
        </ResizablePanelGroup>
      </div>
    </div>
  </SidebarProvider></ChatQuoteContext.Provider>
}
