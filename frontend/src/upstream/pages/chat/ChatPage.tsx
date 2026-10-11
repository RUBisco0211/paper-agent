import { useQuery } from "@tanstack/react-query"
import { usePanelRef } from "react-resizable-panels"
import { useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react"
import { UNSAFE_LocationContext, useLocation, useNavigate, useOutlet } from "react-router-dom"

import { useApi } from "@/lib/api/provider"
import { useAuth } from "@/lib/auth/provider"
import { listBoundSessions } from "@/lib/agent-sessions"
import { SidebarProvider } from "@upstream/components/ui/sidebar"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@upstream/components/ui/resizable"
import { ChatSidebar } from "./ChatSidebar"
import { ChatTabToolbar } from "./ChatTabToolbar"
import { ChatQuoteContext, type ChatQuoteReceiver, type PaperQuoteOpener } from "./ChatQuoteContext"
import type { QuoteReference } from "@upstream/components/chat/quote-references"
import { ProjectPapersPanel } from "./ProjectPapersPanel"
import { chatPath } from "./chat-view"
import { isChatTabPath, isDraftTabPath, readChatTabs, closeChatTab, replaceDraftTab } from "./chat-tabs"

export function ChatPage() {
  const { api } = useApi()
  const { user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const outlet = useOutlet()
  const locationContext = useContext(UNSAFE_LocationContext)
  const cachedPages = useRef(new Map<string, { element: ReactNode; locationContext: typeof locationContext }>())
  const mainRef = useRef<HTMLDivElement>(null)
  const previousPath = useRef<string | null>(null)
  const closingPath = useRef<string | null>(null)
  const storageKey = `paper-agent:chat-tabs:${user?.id ?? "anonymous"}`
  const [tabs, setTabs] = useState(() => readChatTabs(localStorage.getItem(storageKey)))
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
    if (closingPath.current === location.pathname) return
    closingPath.current = null
    const available = new Set(sessions.data.map(chatPath))
    const valid = (path: string) => isDraftTabPath(path) || available.has(path)
    if (location.pathname === "/chat") {
      const restored = [tabs.activePath, ...tabs.paths].find(valid)
      if (restored) navigate(restored, { replace: true })
      return
    }
    if (isChatTabPath(location.pathname) && !valid(location.pathname)) {
      navigate([tabs.activePath, ...tabs.paths].find(valid) ?? "/chat", { replace: true })
      return
    }
    const replacing = (location.state as { replaceDraftTab?: string } | null)?.replaceDraftTab
    setTabs((current) => {
      let paths = current.paths.filter(valid)
      if (replacing && available.has(location.pathname)) paths = replaceDraftTab(paths, replacing, location.pathname)
      else if (isChatTabPath(location.pathname) && valid(location.pathname) && !paths.includes(location.pathname)) paths = [...paths, location.pathname]
      const activePath = paths.includes(location.pathname) ? location.pathname : paths.includes(current.activePath) ? current.activePath : paths[0] ?? "/chat"
      return current.activePath === activePath && current.paths.length === paths.length && current.paths.every((path, index) => path === paths[index]) ? current : { paths, activePath }
    })
  }, [location.pathname, location.state, sessions.isSuccess, sessions.data, navigate, tabs.paths])

  useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify(tabs))
  }, [storageKey, tabs])

  function closeTab(path: string) {
    const next = closeChatTab(tabs.paths, path, location.pathname)
    closingPath.current = path
    setTabs(next)
    if (path === location.pathname) navigate(next.activePath, { replace: true })
  }

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

  if (isChatTabPath(location.pathname) && outlet && closingPath.current !== location.pathname) {
    cachedPages.current.set(location.pathname, { element: outlet, locationContext })
  }
  for (const path of cachedPages.current.keys()) {
    if (!tabs.paths.includes(path) && path !== location.pathname) cachedPages.current.delete(path)
  }
  const main = <div ref={mainRef} className="h-full min-w-0 overflow-hidden bg-background">
    {Array.from(cachedPages.current, ([path, entry]) => (tabs.paths.includes(path) || path === location.pathname && closingPath.current !== path) &&
      <div key={path} aria-hidden={path !== location.pathname} style={{ display: path === location.pathname ? "block" : "none" }} className="h-full min-h-0">
        <UNSAFE_LocationContext.Provider value={entry.locationContext}>{entry.element}</UNSAFE_LocationContext.Provider>
      </div>)}
    {!isChatTabPath(location.pathname) && location.pathname !== "/chat" && outlet}
  </div>

  return <ChatQuoteContext.Provider value={quoteBridge}><SidebarProvider className="min-h-0 flex-1">
    <div className="flex h-full min-h-0 w-full flex-col">
      <ChatTabToolbar paths={tabs.paths} activePath={location.pathname} sessions={sessions.data ?? []} leftOpen={leftOpen} onToggleLeft={() => setLeftOpen((open) => !open)} onSelect={(path) => navigate(path)} onClose={closeTab} />
      <div className="flex min-h-0 flex-1">
        <div aria-hidden={!leftOpen} inert={!leftOpen} className={`h-full shrink-0 overflow-hidden transition-[width,opacity] duration-200 ease-out motion-reduce:transition-none ${leftOpen ? "w-64 opacity-100" : "w-0 opacity-0"}`}>
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
