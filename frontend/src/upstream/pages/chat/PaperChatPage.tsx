import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useParams } from "react-router-dom"

import { useApi } from "@/lib/api/provider"
import { availableChatModels, listBindings, sameSessionId } from "@/lib/agent-sessions"
import { reasoningEffortsForModel } from "./chat-view"
import { ASMessageBubble } from "@upstream/components/chat/ASMessageBubble"
import { CitationProvider } from "@upstream/components/chat/citation-context"
import { TextInput } from "@upstream/components/chat/TextInput"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@upstream/components/ui/select"
import {
  MessageScroller, MessageScrollerButton, MessageScrollerContent,
  MessageScrollerItem, MessageScrollerProvider, MessageScrollerViewport,
} from "@upstream/components/ui/message-scroller"
import { sessionApi } from "@upstream/api/session"
import { useMessages } from "@upstream/hooks/useMessages"
import { BoundCitationSheet } from "./BoundCitationSheet"

export function PaperChatPage() {
  const { agentId = "", sessionId = "" } = useParams()
  const { api } = useApi()
  const queryClient = useQueryClient()
  const [citationId, setCitationId] = useState<string | null>(null)
  const [changingModel, setChangingModel] = useState(false)
  const [modelError, setModelError] = useState("")
  const { msgs, loading, phase, error, reconnecting, historyInterrupted, send, interrupt, onUserConfirm } =
    useMessages(agentId || null, sessionId || null)
  const sessions = useQuery({
    queryKey: ["agent-sessions", agentId],
    queryFn: () => sessionApi.list(agentId),
    enabled: Boolean(agentId),
  })
  const bindings = useQuery({
    queryKey: ["session-bindings"],
    queryFn: () => listBindings(api),
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
  const current = view?.session.config.chat_model_config
  const selectedModel = current ? `${current.credential_id}:${current.model}` : ""
  const availableEfforts = current ? reasoningEffortsForModel(catalog.data?.providers ?? [], current.type, current.model) : []
  const selectedEffort = typeof current?.parameters.reasoning_effort === "string" ? current.parameters.reasoning_effort : "default"

  async function changeModel(value: string) {
    const next = models.data?.find((item) => `${item.credential_id}:${item.model}` === value)
    if (!next) return
    setChangingModel(true)
    setModelError("")
    try {
      await sessionApi.update(sessionId, agentId, { chat_model_config: next })
      await queryClient.invalidateQueries({ queryKey: ["agent-sessions", agentId] })
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
    } catch (cause) {
      setModelError(cause instanceof Error ? cause.message : "切换思考强度失败")
    } finally {
      setChangingModel(false)
    }
  }

  return (
    <CitationProvider onOpen={setCitationId}>
      <main className="flex h-full min-h-0 flex-col">
        <header className="flex items-center justify-between gap-4 border-b bg-background px-5 py-3">
          <div className="min-w-0"><h1 className="truncate font-medium">{view?.session.config.name || "新会话"}</h1>
            <p className="text-xs text-muted-foreground">{binding?.scope === "project" ? project.data?.name ?? "项目" : "全局"}</p>
          </div>
        </header>
        {modelError && <p role="alert" className="px-5 pt-2 text-sm text-destructive">{modelError}</p>}
        {error && <p role="alert" className="px-5 pt-2 text-sm text-destructive">回答失败，请重试</p>}
        {reconnecting && <p role="status" className="px-5 pt-2 text-sm text-muted-foreground">重连中…</p>}
        {historyInterrupted && <p role="status" className="px-5 pt-2 text-sm text-muted-foreground">上次回答已中断，请重新提问</p>}
        <div className="min-h-0 flex-1">
          <MessageScrollerProvider autoScroll defaultScrollPosition="end">
            <MessageScroller><MessageScrollerViewport><MessageScrollerContent className="mx-auto max-w-3xl p-5">
              {loading ? <p className="text-sm text-muted-foreground">加载中…</p> : msgs.length === 0 ? <p className="py-16 text-center text-xl">向文献提问</p> : msgs.map((message) => (
                <MessageScrollerItem key={message.id} messageId={message.id}>
                  <ASMessageBubble message={message} onUserConfirm={onUserConfirm} />
                </MessageScrollerItem>
              ))}
            </MessageScrollerContent></MessageScrollerViewport><MessageScrollerButton /></MessageScroller>
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
            disabled={loading || !binding || !current || changingModel}
            allowedInputTypes={[]}
            fileProcessor={async () => null}
            phase={phase}
            onInterrupt={() => void interrupt()}
          />
        </div>
      </main>
      <BoundCitationSheet sessionId={sessionId} citationId={citationId} onOpenChange={(open) => !open && setCitationId(null)} />
    </CitationProvider>
  )
}
