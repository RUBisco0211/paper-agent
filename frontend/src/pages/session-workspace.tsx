import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Pencil, Trash2, Wifi, WifiOff } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"

import { queryKeys } from "@/app/query"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { CitationSheet } from "@/components/chat/citation-sheet"
import { Composer } from "@/components/chat/composer"
import { EntryList } from "@/components/chat/entry-list"
import { useApi } from "@/lib/api/provider"
import { describeError, notifyError, notifySuccess } from "@/lib/errors"
import { useSessionEvents } from "@/lib/hooks/use-session-events"
import { useLlmConfig } from "@/lib/settings/llm-config-hooks"
import type { Delivery, SessionEvent } from "@/lib/api"

export function SessionWorkspacePage() {
  const { sessionId = "" } = useParams()
  const { api } = useApi()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { config, isReady } = useLlmConfig()

  const [streamingText, setStreamingText] = useState("")
  const [generating, setGenerating] = useState(false)
  const [citationId, setCitationId] = useState<string | null>(null)
  const [renaming, setRenaming] = useState(false)
  const [title, setTitle] = useState("")
  const [confirmDelete, setConfirmDelete] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const session = useQuery({
    queryKey: queryKeys.session(sessionId),
    queryFn: () => api.sessions.detail(sessionId),
    enabled: Boolean(sessionId),
    refetchInterval: (query) => (query.state.data?.is_generating ? 3000 : false),
  })

  const entries = useQuery({
    queryKey: queryKeys.entries(sessionId),
    queryFn: () => api.sessions.entries(sessionId, { limit: 200 }),
    enabled: Boolean(sessionId),
  })

  useEffect(() => {
    setGenerating(session.data?.is_generating ?? false)
  }, [session.data?.is_generating])

  const refreshHistory = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.entries(sessionId) })
    void queryClient.invalidateQueries({ queryKey: queryKeys.session(sessionId) })
  }, [queryClient, sessionId])

  const handleEvent = useCallback(
    (event: SessionEvent) => {
      switch (event.type) {
        case "generation.started":
          setGenerating(true)
          setStreamingText("")
          break
        case "message.delta":
          setStreamingText((prev) => prev + String(event.data.text ?? ""))
          break
        case "queue.updated":
          void queryClient.invalidateQueries({ queryKey: queryKeys.session(sessionId) })
          break
        case "tool.completed":
          refreshHistory()
          break
        case "generation.completed":
        case "generation.aborted":
        case "generation.failed": {
          setGenerating(false)
          setStreamingText("")
          refreshHistory()
          if (event.type === "generation.failed") {
            const code = String(event.data.error_code ?? "internal_error")
            notifyError(new Error(code), "本次生成失败")
          }
          break
        }
        default:
          break
      }
    },
    [queryClient, refreshHistory, sessionId],
  )

  const { connected } = useSessionEvents(sessionId || null, handleEvent)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [entries.data?.items.length, streamingText])

  const send = useMutation({
    mutationFn: (input: { content: string; delivery?: Delivery }) =>
      api.sessions.sendMessage(sessionId, {
        content: input.content,
        delivery: input.delivery,
        // An idle session starts a generation and therefore needs the transient
        // LLM configuration; a busy session just queues the text.
        llm_config: config && isReady ? config : undefined,
      }),
    onSuccess: (result) => {
      if (result.pending) {
        notifySuccess(
          result.pending.delivery === "steering" ? "已加入“调整当前回答”队列" : "已加入追问队列",
          `队列位置 ${result.pending.position}`,
        )
      }
      refreshHistory()
    },
    onError: (error) => notifyError(error, "发送失败"),
  })

  const stop = useMutation({
    mutationFn: () => api.sessions.stop(sessionId),
    onSuccess: () => notifySuccess("已请求停止", "已生成内容会保留"),
    onError: (error) => notifyError(error, "停止失败"),
  })

  const resume = useMutation({
    mutationFn: () => {
      if (!config || !isReady) {
        throw new Error("需要先在模型设置中补全 LLM 配置")
      }
      return api.sessions.resume(sessionId, config)
    },
    onSuccess: refreshHistory,
    onError: (error) => notifyError(error, "继续处理失败"),
  })

  const rename = useMutation({
    mutationFn: (next: string) => api.sessions.rename(sessionId, next),
    onSuccess: () => {
      setRenaming(false)
      void queryClient.invalidateQueries({ queryKey: queryKeys.session(sessionId) })
      void queryClient.invalidateQueries({ queryKey: ["sessions"] })
    },
    onError: (error) => notifyError(error, "改名失败"),
  })

  const remove = useMutation({
    mutationFn: () => api.sessions.remove(sessionId),
    onSuccess: () => {
      notifySuccess("会话已删除")
      void queryClient.invalidateQueries({ queryKey: ["sessions"] })
      navigate("/sessions", { replace: true })
    },
    onError: (error) => notifyError(error, "删除失败"),
  })

  if (session.isError) {
    return (
      <div className="p-6">
        <Alert variant="destructive">
          <AlertTitle>无法打开会话</AlertTitle>
          <AlertDescription>{describeError(session.error)}</AlertDescription>
        </Alert>
      </div>
    )
  }

  const data = session.data
  const pendingCount = (data?.pending.steering ?? 0) + (data?.pending.follow_up ?? 0)

  return (
    <div className="flex h-screen flex-col">
      <header className="border-border/60 flex items-center justify-between gap-4 border-b px-6 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <Button variant="ghost" size="icon" asChild aria-label="返回会话列表">
            <Link to="/sessions">
              <ArrowLeft className="size-4" />
            </Link>
          </Button>
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold">
              {data?.title ?? "未命名会话"}
            </h1>
            <div className="mt-0.5 flex items-center gap-2">
              {data ? (
                data.scope === "project" ? (
                  <Badge variant="outline">
                    项目范围{" "}
                    <Link className="underline" to={`/projects/${data.project_id}`}>
                      查看
                    </Link>
                  </Badge>
                ) : (
                  <Badge variant="outline">个人全库</Badge>
                )
              ) : null}
              <span className="text-muted-foreground flex items-center gap-1 text-xs">
                {connected ? (
                  <>
                    <Wifi className="size-3" /> 事件流已连接
                  </>
                ) : (
                  <>
                    <WifiOff className="size-3" /> 正在重连
                  </>
                )}
              </span>
              {pendingCount > 0 ? (
                <Badge variant="secondary">排队 {pendingCount}</Badge>
              ) : null}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setTitle(data?.title ?? "")
              setRenaming(true)
            }}
          >
            <Pencil className="size-4" />
            改名
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(true)}>
            <Trash2 className="size-4" />
            删除
          </Button>
        </div>
      </header>

      {pendingCount > 0 ? (
        <div className="border-border/60 bg-muted/30 border-b px-6 py-2">
          <p className="text-muted-foreground text-xs">
            尚未投递的消息（按投递时机会成为正式历史）：
            {data?.pending_messages.map((pending) => (
              <span key={pending.id} className="ml-2 inline-flex items-center gap-1">
                <Badge variant="muted">
                  {pending.delivery === "steering" ? "调整" : "追问"} #{pending.position}
                </Badge>
                <span className="max-w-[16rem] truncate">{pending.content}</span>
              </span>
            ))}
          </p>
        </div>
      ) : null}

      <div className="flex-1 overflow-y-auto px-6 py-6">
        {entries.isPending ? (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-16 w-2/3" />
            <Skeleton className="h-16 w-1/2" />
          </div>
        ) : (entries.data?.items.length ?? 0) === 0 && !generating ? (
          <div className="text-muted-foreground flex h-full flex-col items-center justify-center gap-2 text-sm">
            <p>还没有历史消息</p>
            <p>
              {data?.scope === "project"
                ? "本会话只会检索该项目内的论文。"
                : "本会话可以在个人论文库范围内检索。"}
            </p>
          </div>
        ) : (
          <EntryList
            entries={entries.data?.items ?? []}
            streamingText={streamingText}
            generating={generating}
            onCitationClick={setCitationId}
          />
        )}
        <div ref={bottomRef} />
      </div>

      <Composer
        generating={generating}
        pendingCount={pendingCount}
        llmReady={isReady}
        busy={send.isPending || stop.isPending || resume.isPending}
        onSend={(content, delivery) => send.mutate({ content, delivery })}
        onStop={() => stop.mutate()}
        onResume={() => resume.mutate()}
      />

      <CitationSheet
        sessionId={sessionId}
        citationId={citationId}
        onOpenChange={(open) => !open && setCitationId(null)}
      />

      <Dialog open={renaming} onOpenChange={setRenaming}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>会话改名</DialogTitle>
          </DialogHeader>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault()
              rename.mutate(title.trim())
            }}
          >
            <Input value={title} onChange={(event) => setTitle(event.target.value)} required />
            <DialogFooter>
              <Button type="submit" disabled={rename.isPending || !title.trim()}>
                保存
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>删除该会话</DialogTitle>
            <DialogDescription>
              会话历史与排队消息都会被清理；论文库与项目不受影响。正在进行的生成会一并终止。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              取消
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
