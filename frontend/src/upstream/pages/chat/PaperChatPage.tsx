import { useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft } from "lucide-react"
import { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react"
import { Link, useLocation, useNavigate, useParams } from "react-router-dom"

import { useApi } from "@/lib/api/provider"
import { availableChatModels, listBindings, sameSessionId } from "@/lib/agent-sessions"
import { reasoningEffortsForModel } from "./chat-view"
import { MessageNavigationRail } from "./MessageNavigationRail"
import { ChatQuoteContext } from "./ChatQuoteContext"
import { ASMessageBubble } from "@upstream/components/chat/ASMessageBubble"
import { QuoteBadge } from "@upstream/components/chat/QuoteBadge"
import type { QuoteReference } from "@upstream/components/chat/quote-references"
import type { MessageQuote } from "@upstream/components/chat/quote-references"
import { messageQuoteKey, readQuoteReferences } from "@upstream/components/chat/quote-references"
import { restoreRenderedSelection } from "@upstream/components/chat/rendered-selection"
import { AskUserQuestionnaire } from "@upstream/components/chat/AskUserQuestionnaire"
import { CitationProvider } from "@upstream/components/chat/citation-context"
import { DiscoveryImportContext } from "@upstream/components/chat/tool-renderers/PaperDiscoveryRenderer"
import { TextInput } from "@upstream/components/chat/TextInput"
import { Button } from "@upstream/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@upstream/components/ui/select"
import {
  MessageScroller, MessageScrollerContent,
  MessageScrollerItem, MessageScrollerProvider, MessageScrollerViewport,
  useMessageScroller,
} from "@upstream/components/ui/message-scroller"
import { sessionApi } from "@upstream/api/session"
import type { SessionRecord } from "@upstream/api/types"
import { useMessages } from "@upstream/hooks/useMessages"
import { notifyError } from "@/lib/errors"
import { useImportQueue } from "@/lib/import-queue-context"
import { toast } from "sonner"
import type { ToolCallBlock } from "@agentscope-ai/agentscope/message"
import { ProjectScheduleDialog, type ReviewedSchedule } from "@upstream/pages/schedule/ProjectScheduleDialog"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@upstream/components/ui/dialog"

function QuotedMessage({ message, annotations, onQuote, onUserConfirm, activeAnnotationKey, onShowAnnotation, onHideAnnotation, sessionId }: { message: import('@agentscope-ai/agentscope/message').Msg; annotations: MessageQuote[]; onQuote: (reference: QuoteReference) => boolean; onUserConfirm: React.ComponentProps<typeof ASMessageBubble>['onUserConfirm']; activeAnnotationKey: string | null; onShowAnnotation: (key: string) => void; onHideAnnotation: () => void; sessionId: string }) {
  const { scrollToMessage } = useMessageScroller()
  const navigate = useNavigate()
  const quoteBridge = useContext(ChatQuoteContext)
  const openReference = (reference: QuoteReference) => {
    if (reference.kind === 'message') {
      onShowAnnotation(messageQuoteKey(reference))
      scrollToMessage(reference.source_message_id, { align: 'center', behavior: 'smooth' })
      requestAnimationFrame(() => {
        const target = document.querySelector(`[data-quote-message-id="${CSS.escape(reference.source_message_id)}"] [data-quote-block-index="${reference.block_index}"]`)
        if (!target) return
        const root = target.querySelector<HTMLElement>('.cn-markdown')
        const range = root && restoreRenderedSelection(root, { start: reference.start, end: reference.end, text: reference.selected_text })
        range?.startContainer.parentElement?.scrollIntoView({ block: 'center', behavior: 'smooth' })
      })
    } else {
      if (quoteBridge?.openPaper(sessionId, reference)) return
      const query = new URLSearchParams({ page: String(reference.page) })
      if (reference.kind === 'parsed_block' && reference.block_id !== undefined) query.set('block', String(reference.block_id))
      navigate(`/library/${reference.user_paper_id}?${query}`)
    }
  }
  return <div data-quote-message-id={message.id} onClick={(event) => { if (event.target === event.currentTarget) onHideAnnotation() }}><ASMessageBubble message={message} annotations={annotations} activeAnnotationKey={activeAnnotationKey} onUserConfirm={onUserConfirm} onQuote={onQuote} onOpenReference={openReference} /></div>
}

type ImportPreview = {
  candidates: Array<{ title: string | null; identifier: string; source_id: string }>
}

const NO_ANNOTATIONS: MessageQuote[] = []

function scheduleDraft(input: string): ReviewedSchedule | undefined {
  try {
    const value: unknown = JSON.parse(input)
    if (!value || typeof value !== "object") return undefined
    const item = value as Record<string, unknown>
    if (typeof item.name !== "string" || typeof item.prompt !== "string" ||
      typeof item.time !== "string" ||
      (item.weekdays !== undefined && (!Array.isArray(item.weekdays) ||
        !item.weekdays.every((day) => typeof day === "string")))) return undefined
    return {
      name: item.name, prompt: item.prompt, time: item.time,
      weekdays: Array.isArray(item.weekdays) ? item.weekdays : ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
      notify_email: item.notify_email === true,
    }
  } catch { return undefined }
}

export function PaperChatPage({ scheduledRun, scheduledScope }: { scheduledRun?: SessionRecord; scheduledScope?: string } = {}) {
  const params = useParams()
  const agentId = scheduledRun?.agent_id ?? params.agentId ?? ""
  const sessionId = scheduledRun?.id ?? params.sessionId ?? ""
  const { api } = useApi()
  const { setOpen: setImportQueueOpen } = useImportQueue()
  const seenSuccessfulImports = useRef<Set<string> | null>(null)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const [changingModel, setChangingModel] = useState(false)
  const [modelError, setModelError] = useState("")
  const [reviewOpen, setReviewOpen] = useState(false)
  const [reviewBusy, setReviewBusy] = useState(false)
  const [reviewError, setReviewError] = useState("")
  const [pendingQuotes, setPendingQuotes] = useState<QuoteReference[]>([])
  const [activeAnnotationKey, setActiveAnnotationKey] = useState<string | null>(null)
  useEffect(() => {
    const dismiss = (event: MouseEvent) => {
      const target = event.target
      if (target instanceof Element && !target.closest('[data-quote-badge], [data-quote-comment-host], input, textarea, [role="menu"]')) setActiveAnnotationKey(null)
    }
    document.addEventListener('click', dismiss)
    return () => document.removeEventListener('click', dismiss)
  }, [])
  const pendingQuotesRef = useRef(pendingQuotes)
  pendingQuotesRef.current = pendingQuotes
  const quoteBridge = useContext(ChatQuoteContext)
  const addPendingQuote = useCallback((reference: QuoteReference) => {
    if (pendingQuotesRef.current.length >= 8) { toast.error('每次提问最多引用 8 处内容'); return false }
    pendingQuotesRef.current = [...pendingQuotesRef.current, reference]
    setPendingQuotes(pendingQuotesRef.current)
    return true
  }, [])
  useEffect(() => quoteBridge?.register(sessionId, addPendingQuote), [quoteBridge, sessionId, addPendingQuote])
  useEffect(() => { setPendingQuotes([]) }, [sessionId])
  const { msgs, loading, phase, error, reconnecting, historyInterrupted, send, interrupt, onUserConfirm, onExternalAnswer } =
    useMessages(agentId || null, sessionId || null)
  const messageAnnotations = useMemo(() => {
    const bySource = new Map<string, MessageQuote[]>()
    for (const reference of [...msgs.flatMap((item) => readQuoteReferences(item.metadata)), ...pendingQuotes]) {
      if (reference.kind !== 'message') continue
      const existing = bySource.get(reference.source_message_id) ?? []
      existing.push(reference)
      bySource.set(reference.source_message_id, existing)
    }
    return bySource
  }, [msgs, pendingQuotes])
  const pendingQuestion = !loading ? msgs.flatMap((message) => message.role === "assistant"
    ? message.content.filter((block): block is ToolCallBlock => block.type === "tool_call" && block.name === "ask_user" && block.state === "submitted" && !message.content.some((result) => result.type === "tool_result" && result.id === block.id && result.state !== "running")).map((block) => ({ replyId: message.id, toolCall: block }))
    : []).at(-1) : undefined
  const pendingWrite = !loading ? msgs.flatMap((message) => message.role === "assistant"
    ? message.content.filter((block): block is ToolCallBlock => block.type === "tool_call" &&
      (block.name === "import_selected_papers" || block.name === "create_scheduled_task") &&
      block.state === "asking").map((block) => ({ replyId: message.id, toolCall: block }))
    : []).at(-1) : undefined
  const draftInput = pendingWrite?.toolCall.name === "create_scheduled_task" ? pendingWrite.toolCall.input : ""
  const reviewDraft = useMemo(() => scheduleDraft(draftInput), [draftInput])
  const importPreview = useQuery({
    queryKey: ["import-approval-preview", sessionId, pendingWrite?.toolCall.id],
    queryFn: () => api.client.request<ImportPreview>("/v1/imports/approvals/latest", { query: { session_id: sessionId } }),
    enabled: reviewOpen && pendingWrite?.toolCall.name === "import_selected_papers",
    retry: false,
  })

  async function confirmWrite(edited?: ReviewedSchedule) {
    if (!pendingWrite || reviewBusy) return
    setReviewBusy(true)
    setReviewError("")
    try {
      const toolCall = edited
        ? { ...pendingWrite.toolCall, input: JSON.stringify(edited) }
        : pendingWrite.toolCall
      await onUserConfirm(toolCall, true, pendingWrite.replyId)
      setReviewOpen(false)
    } catch {
      setReviewError("确认失败，请重试")
      if (edited) throw new Error("确认失败，请重试")
    } finally {
      setReviewBusy(false)
    }
  }

  async function rejectWrite() {
    if (!pendingWrite || reviewBusy) return
    setReviewBusy(true)
    setReviewError("")
    try {
      await onUserConfirm(pendingWrite.toolCall, false, pendingWrite.replyId)
      setReviewOpen(false)
    } catch {
      setReviewError("拒绝失败，请重试")
    } finally {
      setReviewBusy(false)
    }
  }
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

  useEffect(() => {
    if (loading) return
    const successful = msgs.flatMap((message) => {
      const calls = new Set(message.content.filter((block) => block.type === "tool_call" && block.name === "import_selected_papers").map((block) => block.id))
      return message.content.filter((block) => block.type === "tool_result" && block.state === "success" && calls.has(block.id)).map((block) => block.id)
    })
    const ids = new Set(successful)
    if (seenSuccessfulImports.current === null) { seenSuccessfulImports.current = ids; return }
    if (successful.some((id) => !seenSuccessfulImports.current!.has(id))) {
      toast.info("文献已加入入库队列")
      setImportQueueOpen(true)
    }
    seenSuccessfulImports.current = ids
  }, [loading, msgs, setImportQueueOpen])

  async function importSelected(tokens: string[]) {
    await api.imports.approve(sessionId, tokens)
    const now = new Date().toISOString()
    await send([{ id: crypto.randomUUID(), type: "text", text: "请调用 import_selected_papers 导入我刚刚确认的文献，并汇报每篇结果。", created_at: now, finished_at: now }])
  }

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
    <DiscoveryImportContext.Provider value={importSelected}><CitationProvider onOpen={(id) => void openCitation(id)}>
      <main className="flex h-full min-h-0 flex-col">
        {scheduledRun && <header data-slot="app-toolbar" className="flex h-(--app-toolbar-height) shrink-0 items-center justify-between gap-4 border-b bg-background px-5">
          <div className="flex min-w-0 items-center gap-2">
            {scheduledRun && <Button asChild variant="ghost" size="icon-sm"><Link to="/scheduled" aria-label="返回月视图"><ArrowLeft className="size-4" /></Link></Button>}
            <div className="min-w-0"><h1 className="truncate font-medium">{scheduledRun?.config.name || view?.session.config.name || "新会话"}</h1>
            <p className="text-xs text-muted-foreground">{scheduledScope ?? (binding?.scope === "project" ? project.data?.name ?? "项目" : "全局")}</p>
            </div>
          </div>
        </header>}
        {modelError && <p role="alert" className="px-5 pt-2 text-sm text-destructive">{modelError}</p>}
        {!current && !models.isPending && <p role="status" className="px-5 pt-2 text-sm text-muted-foreground">请选择模型后发送</p>}
        {!scheduledRun && !binding && !bindings.isPending && <p role="status" className="px-5 pt-2 text-sm text-muted-foreground">会话尚未就绪，请刷新重试</p>}
        {error && <p role="alert" className="px-5 pt-2 text-sm text-destructive">回答失败，请重试</p>}
        {reconnecting && <p role="status" className="px-5 pt-2 text-sm text-muted-foreground">重连中…</p>}
        {historyInterrupted && <p role="status" className="px-5 pt-2 text-sm text-muted-foreground">上次回答已中断，请重新提问</p>}
        <div className="min-h-0 flex-1">
          <MessageScrollerProvider autoScroll defaultScrollPosition="end">
            <MessageScroller><MessageScrollerViewport className="no-scrollbar scrollbar-none! scrollbar-gutter-auto!"><MessageScrollerContent className="mx-auto max-w-(--chat-content-max-width) p-5">
              {loading ? <p className="text-sm text-muted-foreground">加载中…</p> : msgs.length === 0 ? <p className="py-16 text-center text-xl">向文献提问</p> : msgs.map((message) => (
                <MessageScrollerItem key={message.id} messageId={message.id}>
                  <QuotedMessage message={message} annotations={messageAnnotations.get(message.id) ?? NO_ANNOTATIONS} activeAnnotationKey={activeAnnotationKey} onShowAnnotation={setActiveAnnotationKey} onHideAnnotation={() => setActiveAnnotationKey(null)} sessionId={sessionId} onUserConfirm={onUserConfirm} onQuote={addPendingQuote} />
                </MessageScrollerItem>
              ))}
            </MessageScrollerContent></MessageScrollerViewport><MessageNavigationRail messages={loading ? [] : msgs} /></MessageScroller>
          </MessageScrollerProvider>
        </div>
        {pendingQuestion && <div className="mx-auto w-full max-w-(--chat-content-max-width) px-4 pb-2">
          <AskUserQuestionnaire key={pendingQuestion.toolCall.id} toolCall={pendingQuestion.toolCall} onAnswer={(answers) => onExternalAnswer(pendingQuestion.toolCall, pendingQuestion.replyId, answers)} />
        </div>}
        {pendingWrite && <div className="mx-auto w-full max-w-(--chat-content-max-width) px-4 pb-2 text-sm">
          <div data-slot="tool-confirmation" className="space-y-3 rounded-lg bg-muted ring-1 ring-border">
            <strong>{pendingWrite.toolCall.name === "import_selected_papers" ? "文献入库等待确认" : "定时任务等待确认"}</strong>
            <p className="text-muted-foreground">查看内容后确认，或拒绝本次操作。</p>
            <div className="flex items-center gap-2">
              <Button type="button" size="sm" onClick={() => { setReviewError(""); setReviewOpen(true) }}>查看并确认</Button>
              <Button type="button" size="sm" variant="ghost" disabled={reviewBusy} onClick={() => void rejectWrite()}>拒绝</Button>
            </div>
            {reviewError && <p role="alert" className="text-destructive">{reviewError}</p>}
          </div>
        </div>}
        <div className="mx-auto w-full max-w-(--chat-content-max-width) p-4">
          <TextInput
            className="w-full"
            headerSlot={<div className="flex items-center gap-2 px-2 py-1">
              <Select value={selectedModel} onValueChange={(value) => void changeModel(value)} disabled={changingModel || phase !== "idle"}>
                <SelectTrigger className="max-w-56"><SelectValue placeholder="选择模型" /></SelectTrigger>
                <SelectContent>{models.data?.map((item) => <SelectItem key={`${item.credential_id}:${item.model}`} value={`${item.credential_id}:${item.model}`}>{item.type.replace(/_credential$/, "")} · {item.model}</SelectItem>)}</SelectContent>
              </Select>
              {availableEfforts.length > 0 && <Select value={selectedEffort} onValueChange={(value) => void changeEffort(value)} disabled={changingModel || phase !== "idle"}>
                <SelectTrigger className="h-8 w-32 border-0 bg-transparent text-xs" aria-label="思考强度"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="default">默认思考</SelectItem>{availableEfforts.map((effort) => <SelectItem key={effort} value={effort}>{effort}</SelectItem>)}</SelectContent>
              </Select>}
            </div>}
            quoteSlot={pendingQuotes.length ? <>
              {pendingQuotes.map((reference, index) => <QuoteBadge key={index} reference={reference}
                onEdit={(comment) => setPendingQuotes((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, comment } : item))}
                onRemove={() => setPendingQuotes((current) => current.filter((_, item) => item !== index))} />)}
            </> : undefined}
            allowEmptyText={pendingQuotes.length > 0}
            onSend={async (blocks) => {
              const sent = await (pendingQuotes.length ? send(blocks, pendingQuotes) : send(blocks))
              if (sent) setPendingQuotes([])
              return sent
            }}
            sendDisabled={loading || changingModel || (!binding && !scheduledRun) || !current}
            allowedInputTypes={[]}
            fileProcessor={async () => null}
            phase={phase}
            onInterrupt={() => void interrupt()}
          />
        </div>
        {pendingWrite?.toolCall.name === "import_selected_papers" && <Dialog open={reviewOpen} onOpenChange={setReviewOpen}>
          <DialogContent className="sm:max-w-lg">
            <DialogHeader><DialogTitle>确认文献入库</DialogTitle><DialogDescription>确认后，所列文献将加入入库队列。</DialogDescription></DialogHeader>
            <div className="max-h-[50vh] space-y-2 overflow-y-auto text-sm">
              <p className="text-muted-foreground">{binding?.project_id ? `添加到项目：${project.data?.name ?? "项目"}` : "添加到全局文献库"}</p>
              {importPreview.isPending && <p>加载中…</p>}
              {importPreview.isError && <p role="alert" className="text-destructive">选文信息不可用，请重新选择文献</p>}
              {importPreview.data?.candidates.map((item) => <div key={item.identifier} className="border-b py-2">
                <p className="font-medium">{item.title || item.identifier}</p>
                <p className="text-muted-foreground">{item.identifier}</p>
                <a href={item.source_id} target="_blank" rel="noopener noreferrer" className="text-muted-foreground underline">查看来源</a>
              </div>)}
              {reviewError && <p role="alert" className="text-destructive">{reviewError}</p>}
            </div>
            <DialogFooter><Button type="button" variant="outline" onClick={() => setReviewOpen(false)}>关闭</Button><Button type="button" disabled={reviewBusy || !importPreview.data?.candidates.length} onClick={() => void confirmWrite()}>确认入库</Button></DialogFooter>
          </DialogContent>
        </Dialog>}
        {pendingWrite?.toolCall.name === "create_scheduled_task" && reviewDraft && <ProjectScheduleDialog
          projects={binding?.project_id && project.data ? [{ id: binding.project_id, name: project.data.name }] : []}
          projectId={binding?.project_id ?? ""}
          onProjectChange={() => {}}
          models={[]}
          open={reviewOpen}
          onOpenChange={setReviewOpen}
          review={reviewDraft}
          onReview={confirmWrite}
        />}
      </main>
    </CitationProvider></DiscoveryImportContext.Provider>
  )
}
