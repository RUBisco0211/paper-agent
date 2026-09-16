import { ArrowUp, Clock, CornerDownLeft, Square, Undo2 } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router-dom"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import type { Delivery } from "@/lib/api"

/**
 * Composer for one session.
 *
 * While a generation runs, new input is explained as either "adjust the current
 * answer" (steering) or "queue a follow-up"; the distinction changes when the
 * message is delivered, so the UI never shows one text as both.
 */
export function Composer({
  generating,
  pendingCount,
  llmReady,
  busy,
  onSend,
  onStop,
  onResume,
}: {
  generating: boolean
  pendingCount: number
  llmReady: boolean
  busy: boolean
  onSend: (content: string, delivery?: Delivery) => void
  onStop: () => void
  onResume: () => void
}) {
  const [content, setContent] = useState("")

  function submit(delivery?: Delivery) {
    const trimmed = content.trim()
    if (!trimmed || busy) {
      return
    }
    onSend(trimmed, delivery)
    setContent("")
  }

  return (
    <div className="border-border/60 flex flex-col gap-2 border-t p-4">
      {!llmReady ? (
        <Alert>
          <AlertDescription>
            还没有可用的模型配置，空闲会话无法发起生成。请先到{" "}
            <Link className="underline" to="/settings">
              模型设置
            </Link>{" "}
            填写 Provider、模型与 API Key。
          </AlertDescription>
        </Alert>
      ) : null}

      {pendingCount > 0 && !generating ? (
        <div className="flex items-center justify-between rounded-md border border-dashed px-3 py-2">
          <span className="text-muted-foreground flex items-center gap-2 text-sm">
            <Clock className="size-4" />
            有 {pendingCount} 条排队消息尚未投递（停止或中断后需要手动继续）
          </span>
          <Button size="sm" variant="outline" disabled={busy || !llmReady} onClick={onResume}>
            <Undo2 className="size-4" />
            继续处理排队消息
          </Button>
        </div>
      ) : null}

      <Textarea
        value={content}
        placeholder={
          generating
            ? "输入新内容：可以调整当前回答，或排队追问"
            : "针对授权范围内的论文提问，例如：这篇论文的核心贡献是什么？"
        }
        className="max-h-40 min-h-20 resize-none"
        onChange={(event) => setContent(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault()
            submit()
          }
        }}
      />
      <div className="flex items-center justify-between gap-2">
        <div className="text-muted-foreground flex items-center gap-2 text-xs">
          <Badge variant="outline">Enter 发送 · Shift+Enter 换行</Badge>
          {generating ? <Badge variant="outline">生成中</Badge> : null}
        </div>
        <div className="flex items-center gap-2">
          {generating ? (
            <>
              <Button
                size="sm"
                variant="outline"
                disabled={busy || !content.trim()}
                onClick={() => submit("steering")}
              >
                <CornerDownLeft className="size-4" />
                调整当前回答
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={busy || !content.trim()}
                onClick={() => submit("follow_up")}
              >
                <Clock className="size-4" />
                排队追问
              </Button>
              <Button size="sm" variant="destructive" onClick={onStop}>
                <Square className="size-4" />
                停止
              </Button>
            </>
          ) : (
            <Button
              size="sm"
              disabled={busy || !content.trim() || !llmReady}
              onClick={() => submit()}
            >
              <ArrowUp className="size-4" />
              发送
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
