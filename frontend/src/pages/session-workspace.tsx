import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Pencil, Trash2 } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"

import { PageHeader } from "@/app/app-shell"

import { queryKeys } from "@/app/query"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { CitationSheet } from "@/components/chat/citation-sheet"
import { Composer } from "@/components/chat/composer"
import { MessageThread } from "@/components/chat/message-thread"
import { useApi } from "@/lib/api/provider"
import { describeError, notifyError, notifySuccess } from "@/lib/errors"
import { useSessionEvents } from "@/lib/hooks/use-session-events"
import { useLlmConfig } from "@/lib/settings/llm-config-hooks"
import type { Delivery, SessionEvent } from "@/lib/api"

const SCOPE_LABEL: Record<string, string> = {
  library: "全局",
  project: "项目",
  paper: "单篇文献",
}

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

  useSessionEvents(sessionId || null, handleEvent)

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
    onSuccess: () => notifySuccess("已停止"),
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
    onError: (error) => notifyError(error, "重命名失败"),
  })

  const remove = useMutation({
    mutationFn: () => api.sessions.remove(sessionId),
    onSuccess: () => {
      notifySuccess("会话已删除")
      void queryClient.invalidateQueries({ queryKey: ["sessions"] })
      navigate("/library", { replace: true })
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
    <div className="flex h-full min-h-0 flex-col">
      {/* 与其他页面共用 PageHeader，顶栏高度保持一致 */}
      <PageHeader
        title={data?.title ?? "未命名会话"}
        leading={
          <Button variant="ghost" size="icon" aria-label="返回" onClick={() => navigate(-1)}>
            <ArrowLeft />
          </Button>
        }
        actions={
          <>
            {data ? <Badge variant="outline">{SCOPE_LABEL[data.scope]}</Badge> : null}
            {pendingCount > 0 ? (
              <Badge variant="secondary">待发送 {pendingCount}</Badge>
            ) : null}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setTitle(data?.title ?? "")
                setRenaming(true)
              }}
            >
              <Pencil data-icon="inline-start" />
              重命名
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(true)}>
              <Trash2 data-icon="inline-start" />
              删除
            </Button>
          </>
        }
      />

      <div className="min-h-0 flex-1">
        {entries.isPending ? (
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-3 p-4">
            <Skeleton className="h-16 w-2/3" />
            <Skeleton className="h-16 w-1/2" />
          </div>
        ) : (
          <MessageThread
            entries={entries.data?.items ?? []}
            streamingText={streamingText}
            generating={generating}
            onCitationClick={setCitationId}
          />
        )}
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
            <DialogTitle>重命名会话</DialogTitle>
          </DialogHeader>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault()
              rename.mutate(title.trim())
            }}
          >
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="session-title">标题</FieldLabel>
                <Input
                  id="session-title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  required
                />
              </Field>
            </FieldGroup>
            <DialogFooter>
              <Button type="submit" disabled={rename.isPending || !title.trim()}>
                {rename.isPending ? <Spinner data-icon="inline-start" /> : null}
                保存
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除该会话？</AlertDialogTitle>
            <AlertDialogDescription>
              会话内容会被删除，文献库和项目不受影响。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => remove.mutate()}>删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
