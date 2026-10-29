import { useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft } from "lucide-react"
import { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react"
import { Link, useLocation, useNavigate, useParams } from "react-router-dom"

import { useApi } from "@/components/providers/ApiProvider"
import { availableChatModels, listBindings, sameSessionId } from "@/lib/agentSessions"
import { reasoningEffortsForModel } from "@/components/chat/chatView"
import { MessageNavigationRail } from "@/components/chat/MessageNavigationRail"
import { ChatQuoteContext } from "@/components/chat/chatQuoteContext"
import { MessageBubble } from "@/components/chat/MessageBubble"
import { QuoteBadge } from "@/components/chat/QuoteBadge"
import type { MessageQuote, PaperOpenReference, QuoteReference } from "@/types/chat"
import type { MentionCandidate } from "@/lib/mentions"
import type { ImportApprovalPreview } from "@/types/business"
import { messageQuoteKey, readQuoteReferences } from "@/components/chat/quoteReferences"
import { restoreRenderedSelection } from "@/components/chat/renderedSelection"
import { AskUserQuestionnaire } from "@/components/chat/AskUserQuestionnaire"
import { CitationProvider } from "@/components/chat/CitationProvider"
import { CitationDetailDialog, type CitationBlock } from "@/components/chat/CitationDetailDialog"
import { DiscoveryImportContext } from "@/components/chat/toolRenderers/PaperDiscoveryRenderer"
import { TextInput } from "@/components/chat/TextInput"
import { Button } from "@/components/ui/Button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/Select"
import {
  MessageScroller, MessageScrollerContent,
  MessageScrollerItem, MessageScrollerProvider, MessageScrollerViewport,
  useMessageScroller,
} from "@/components/ui/MessageScroller"
import { sessionApi } from "@/lib/api/agentscope/session"
import type { SessionRecord } from "@/types/agent"
import { useMessages } from "@/hooks/useMessages"
import { notifyError } from "@/lib/errors"
import { useImportQueue } from "@/components/providers/ImportQueueProvider"
import { toast } from "sonner"
import type { ToolCallBlock } from "@agentscope-ai/agentscope/message"
import { ProjectScheduleDialog } from "@/components/schedule/ScheduleDialog"
import type { ReviewedSchedule } from "@/types/schedule"
import { DAY_CODES } from "@/components/schedule/scheduleFrequency"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/Dialog"

function QuotedMessage({ message, annotations, onQuote, onUserConfirm, activeAnnotationKey, onShowAnnotation, onHideAnnotation, sessionId }: { message: import('@agentscope-ai/agentscope/message').Msg; annotations: MessageQuote[]; onQuote: (reference: QuoteReference) => boolean; onUserConfirm: React.ComponentProps<typeof MessageBubble>['onUserConfirm']; activeAnnotationKey: string | null; onShowAnnotation: (key: string) => void; onHideAnnotation: () => void; sessionId: string }) {
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
  return <div data-quote-message-id={message.id} onClick={(event) => { if (event.target === event.currentTarget) onHideAnnotation() }}><MessageBubble message={message} annotations={annotations} activeAnnotationKey={activeAnnotationKey} onUserConfirm={onUserConfirm} onQuote={onQuote} onOpenReference={openReference} /></div>
}

const NO_ANNOTATIONS: MessageQuote[] = []

/** Hands the scroller's imperative API to the page, which renders outside the provider. */
function ScrollerBridge({ onReady }: { onReady: (api: ReturnType<typeof useMessageScroller>) => void }) {
  const api = useMessageScroller()
  useEffect(() => { onReady(api) }, [api, onReady])
  return null
}

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
      weekdays: Array.isArray(item.weekdays) ? item.weekdays : [...DAY_CODES],
      notify_email: item.notify_email === true,
    }
  } catch { return undefined }
}

export function PaperChatPage({ scheduledRun, scheduledScope, scheduledProjectId }: { scheduledRun?: SessionRecord; scheduledScope?: string; scheduledProjectId?: string } = {}) {
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
  const [citationDetail, setCitationDetail] = useState<{
    paperId: string
    fallbackPage: number | null
    snippet?: string
    blocks: CitationBlock[]
  } | null>(null)
  const [pendingQuotes, setPendingQuotes] = useState<QuoteReference[]>([])
  const [mentions, setMentions] = useState<MentionCandidate[]>([])
  const scroller = useRef<ReturnType<typeof useMessageScroller> | null>(null)
  const rememberScroller = useCallback((api: ReturnType<typeof useMessageScroller>) => { scroller.current = api }, [])
  const citationRequestToken = useRef(0)
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
  useEffect(() => { setPendingQuotes([]); setMentions([]) }, [sessionId])
  useEffect(() => {
    setCitationDetail(null)
    // Invalidate responses still in flight for the session being left.
    citationRequestToken.current += 1
  }, [sessionId])
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
    queryFn: () => api.client.request<ImportApprovalPreview>("/v1/imports/approvals/latest", { query: { session_id: sessionId } }),
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
  // @ 提及只提供本会话范围内的文献：有项目按项目取，否则取全局。
  const mentionScope = scheduledRun ? scheduledProjectId ?? "" : binding?.project_id ?? ""
  const mentionCandidatesQuery = useQuery({
    queryKey: ["mention-candidates", mentionScope || "library"],
    queryFn: async () => {
      const page = mentionScope
        ? await api.projects.papers(mentionScope, { limit: 200 })
        : await api.library.list({ limit: 200 })
      return page.items.map((item) => ({
        user_paper_id: item.id,
        title: item.title || "未命名文献",
      }))
    },
    enabled: scheduledRun ? true : !bindings.isPending,
  })
  const mentionCandidates = mentionCandidatesQuery.data ?? []
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
    const requestedSession = sessionId
    const requestToken = ++citationRequestToken.current
    try {
      const citation = await api.client.request<{
        paper_id: string
        snippet?: string
        page_start: number | null
        source_locations?: Array<{ block_id: number; page?: number | null }>
      }>(`/v1/session-bindings/${sessionId}/citations/${citationId}`)
      if (requestToken !== citationRequestToken.current || requestedSession !== sessionId) return
      setCitationDetail({
        paperId: citation.paper_id,
        fallbackPage: citation.page_start,
        snippet: citation.snippet,
        blocks: citation.source_locations ?? [],
      })
    } catch (error) {
      if (requestToken !== citationRequestToken.current || requestedSession !== sessionId) return
      notifyError(error, "无法读取引用详情")
    }
  }

  function openPaperEntry(reference: PaperOpenReference) {
    const opened = quoteBridge?.openPaper(sessionId, {
      kind: reference.kind === "paper" ? "parsed_block" : reference.kind,
      user_paper_id: reference.user_paper_id,
      version: "",
      page: reference.page ?? 0,
      block_id: reference.block_id,
      selected_text: reference.selected_text ?? "",
      comment: reference.comment ?? "",
    }) ?? false
    // A bare entry has no locator; the sidebar still knows how to show it.
    return opened || reference.kind === "paper"
  }

  function openCitationBlock(blockId: number, page?: number | null) {
    const detail = citationDetail
    if (!detail) return
    // The block belongs to the conversation: show it in the sidebar reader
    // first and only leave the chat when nothing there can take it.
    const opened = quoteBridge?.openPaper(sessionId, {
      kind: "parsed_block",
      user_paper_id: detail.paperId,
      version: "",
      page: page ?? detail.fallbackPage ?? 0,
      block_id: blockId,
      selected_text: detail.snippet ?? "",
      comment: "",
    })
    if (opened) {
      setCitationDetail(null)
      return
    }
    const params = new URLSearchParams()
    const targetPage = page ?? detail.fallbackPage
    if (targetPage) params.set("page", String(targetPage))
    params.set("block", String(blockId))
    setCitationDetail(null)
    navigate(`/library/${detail.paperId}?${params}`, {
      state: { from: location.pathname },
    })
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
    <DiscoveryImportContext.Provider value={importSelected}><CitationProvider
      onOpen={(id) => void openCitation(id)}
      onOpenPaper={openPaperEntry}
    >
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
            </MessageScrollerContent></MessageScrollerViewport><MessageNavigationRail messages={loading ? [] : msgs} /><ScrollerBridge onReady={rememberScroller} /></MessageScroller>
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
            mentionCandidates={mentionCandidates}
            onMentions={setMentions}
            onSend={async (blocks) => {
              const sent = await send(blocks, pendingQuotes, mentions)
              if (sent) {
                setPendingQuotes([])
                // The optimistic message is appended below the fold; follow it.
                scroller.current?.scrollToEnd({ behavior: "smooth" })
              }
              return sent
            }}
            sendDisabled={loading || changingModel || (!binding && !scheduledRun) || !current}
            allowedInputTypes={[]}
            fileProcessor={async () => null}
            phase={phase}
            onInterrupt={() => void interrupt()}
          />
        </div>
        <CitationDetailDialog
          open={citationDetail !== null}
          blocks={citationDetail?.blocks ?? []}
          snippet={citationDetail?.snippet}
          onOpenChange={(open) => { if (!open) setCitationDetail(null) }}
          onOpenBlock={openCitationBlock}
        />
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
