import { useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, PanelRightClose, PanelRightOpen } from "lucide-react"
import { useState } from "react"
import { Link, useLocation, useNavigate, useOutletContext, useParams } from "react-router-dom"

import { useApi } from "@/lib/api/provider"
import { availableChatModels, listBindings, sameSessionId } from "@/lib/agent-sessions"
import { reasoningEffortsForModel } from "./chat-view"
import { MessageNavigationRail } from "./MessageNavigationRail"
import { ASMessageBubble } from "@upstream/components/chat/ASMessageBubble"
import { CitationProvider } from "@upstream/components/chat/citation-context"
import { TextInput } from "@upstream/components/chat/TextInput"
import { Button } from "@upstream/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@upstream/components/ui/select"
import {
  MessageScroller, MessageScrollerContent,
  MessageScrollerItem, MessageScrollerProvider, MessageScrollerViewport,
} from "@upstream/components/ui/message-scroller"
import { sessionApi } from "@upstream/api/session"
import type { SessionRecord } from "@upstream/api/types"
import { useMessages } from "@upstream/hooks/useMessages"
import { notifyError } from "@/lib/errors"

export function PaperChatPage({ scheduledRun, scheduledScope }: { scheduledRun?: SessionRecord; scheduledScope?: string } = {}) {
  const params = useParams()
  const agentId = scheduledRun?.agent_id ?? params.agentId ?? ""
  const sessionId = scheduledRun?.id ?? params.sessionId ?? ""
  const { api } = useApi()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const papersPanel = useOutletContext<{ papersOpen: boolean; togglePapers: () => void; projectId: string | null } | undefined>()
  const [changingModel, setChangingModel] = useState(false)
  const [modelError, setModelError] = useState("")
  const { msgs, loading, phase, error, reconnecting, historyInterrupted, send, interrupt, onUserConfirm } =
    useMessages(agentId || null, sessionId || null)
  const sessions = useQuery({
    queryKey: ["agent-sessions", agentId],
    queryFn: () => sessionApi.list(agentId),
    enabled: Boolean(agentId && !scheduledRun),
  })
  const bindings = useQuery({
    queryKey: ["session-bindings"],
    queryFn: () => listBindings(api),
    enabled: !scheduledRun,
  })
  const models = useQuery({
    queryKey: ["available-chat-models"],
    queryFn: () => availableChatModels(api),
  })
  const catalog = useQuery({
    queryKey: ["llm-catalog"],
    queryFn: api.sessions.llmCatalog,
  })
  const view = sessions.data?.sessions.find((item) => sameSessionId(item.session.id, sessionId))
  const binding = bindings.data?.find((item) => sameSessionId(item.session_id, sessionId))
  const project = useQuery({
    queryKey: ["project", binding?.project_id],
    queryFn: () => api.projects.detail(binding!.project_id!),
    enabled: Boolean(binding?.project_id),
  })
  const current = (scheduledRun ?? view?.session)?.config.chat_model_config
  const selectedModel = current ? `${current.credential_id}:${current.model}` : ""
  const availableEfforts = current ? reasoningEffortsForModel(catalog.data?.providers ?? [], current.type, current.model) : []
  const selectedEffort = typeof current?.parameters.reasoning_effort === "string" ? current.parameters.reasoning_effort : "default"

  async function openCitation(citationId: string) {
    try {
      const citation = await api.client.request<{
        paper_id: string
        page_start: number | null
        source_locations?: Array<{ source_ranges?: Array<{ block_id: number; page?: number }> }>
      }>(`/v1/session-bindings/${sessionId}/citations/${citationId}`)
      const source = citation.source_locations?.flatMap((item) => item.source_ranges ?? [])[0]
      const params = new URLSearchParams()
      const page = source?.page ?? citation.page_start
      if (page) params.set("page", String(page))
      if (source) params.set("block", String(source.block_id))
      navigate(`/library/${citation.paper_id}${params.size ? `?${params}` : ""}`, {
        state: { from: location.pathname },
      })
    } catch (error) {
      notifyError(error, "无法打开引用原文")
    }
  }

  async function changeModel(value: string) {
    const next = models.data?.find((item) => `${item.credential_id}:${item.model}` === value)
    if (!next) return
    setChangingModel(true)
    setModelError("")
    try {
      await sessionApi.update(sessionId, agentId, { chat_model_config: next })
      await queryClient.invalidateQueries({ queryKey: ["agent-sessions", agentId] })
      if (scheduledRun) await queryClient.invalidateQueries({ queryKey: ["schedule-runs", scheduledRun.source_schedule_id] })
    } catch (cause) {
      setModelError(cause instanceof Error ? cause.message : "切换模型失败")
    } finally {
      setChangingModel(false)
    }
  }

  async function changeEffort(value: string) {
    if (!current) return
    setChangingModel(true)
    setModelError("")
    const parameters = { ...current.parameters }
    if (value === "default") delete parameters.reasoning_effort
    else parameters.reasoning_effort = value
    try {
      await sessionApi.update(sessionId, agentId, { chat_model_config: { ...current, parameters } })
      await queryClient.invalidateQueries({ queryKey: ["agent-sessions", agentId] })
      if (scheduledRun) await queryClient.invalidateQueries({ queryKey: ["schedule-runs", scheduledRun.source_schedule_id] })
    } catch (cause) {
      setModelError(cause instanceof Error ? cause.message : "切换思考强度失败")
    } finally {
      setChangingModel(false)
    }
  }

  return (
    <CitationProvider onOpen={(id) => void openCitation(id)}>
      <main className="flex h-full min-h-0 flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b bg-background px-5">
          <div className="flex min-w-0 items-center gap-2">
            {scheduledRun && <Button asChild variant="ghost" size="icon-sm"><Link to="/scheduled" aria-label="返回月视图"><ArrowLeft className="size-4" /></Link></Button>}
            <div className="min-w-0"><h1 className="truncate font-medium">{scheduledRun?.config.name || view?.session.config.name || "新会话"}</h1>
            <p className="text-xs text-muted-foreground">{scheduledScope ?? (binding?.scope === "project" ? project.data?.name ?? "项目" : "全局")}</p>
            </div>
          </div>
          {!scheduledRun && papersPanel?.projectId && <Button variant="ghost" size="icon-sm" aria-label={papersPanel.papersOpen ? "收起项目文献" : "展开项目文献"} onClick={papersPanel.togglePapers}>{papersPanel.papersOpen ? <PanelRightClose /> : <PanelRightOpen />}</Button>}
        </header>
        {modelError && <p role="alert" className="px-5 pt-2 text-sm text-destructive">{modelError}</p>}
        {error && <p role="alert" className="px-5 pt-2 text-sm text-destructive">回答失败，请重试</p>}
        {reconnecting && <p role="status" className="px-5 pt-2 text-sm text-muted-foreground">重连中…</p>}
        {historyInterrupted && <p role="status" className="px-5 pt-2 text-sm text-muted-foreground">上次回答已中断，请重新提问</p>}
        <div className="min-h-0 flex-1">
          <MessageScrollerProvider autoScroll defaultScrollPosition="end">
            <MessageScroller><MessageScrollerViewport className="no-scrollbar ![scrollbar-width:none] ![scrollbar-gutter:auto]"><MessageScrollerContent className="mx-auto max-w-3xl p-5">
              {loading ? <p className="text-sm text-muted-foreground">加载中…</p> : msgs.length === 0 ? <p className="py-16 text-center text-xl">向文献提问</p> : msgs.map((message) => (
                <MessageScrollerItem key={message.id} messageId={message.id}>
                  <ASMessageBubble message={message} onUserConfirm={onUserConfirm} />
                </MessageScrollerItem>
              ))}
            </MessageScrollerContent></MessageScrollerViewport><MessageNavigationRail messages={loading ? [] : msgs} /></MessageScroller>
          </MessageScrollerProvider>
        </div>
        <div className="mx-auto w-full max-w-3xl p-4">
          <TextInput
            className="w-full rounded-[32px] bg-muted p-1"
            headerSlot={<div className="flex items-center gap-2 px-2 py-1">
              <Select value={selectedModel} onValueChange={(value) => void changeModel(value)} disabled={changingModel || phase !== "idle"}>
                <SelectTrigger className="h-8 max-w-56 border-0 bg-transparent text-xs"><SelectValue placeholder="选择模型" /></SelectTrigger>
                <SelectContent>{models.data?.map((item) => <SelectItem key={`${item.credential_id}:${item.model}`} value={`${item.credential_id}:${item.model}`}>{item.type.replace(/_credential$/, "")} · {item.model}</SelectItem>)}</SelectContent>
              </Select>
              {availableEfforts.length > 0 && <Select value={selectedEffort} onValueChange={(value) => void changeEffort(value)} disabled={changingModel || phase !== "idle"}>
                <SelectTrigger className="h-8 w-32 border-0 bg-transparent text-xs" aria-label="思考强度"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="default">默认思考</SelectItem>{availableEfforts.map((effort) => <SelectItem key={effort} value={effort}>{effort}</SelectItem>)}</SelectContent>
              </Select>}
            </div>}
            onSend={(blocks) => void send(blocks)}
            disabled={loading || (!binding && !scheduledRun) || !current || changingModel}
            allowedInputTypes={[]}
            fileProcessor={async () => null}
            phase={phase}
            onInterrupt={() => void interrupt()}
          />
        </div>
      </main>
    </CitationProvider>
  )
}
