import { ArrowUp, Clock, CornerDownLeft, Square } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router-dom"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import type { Delivery } from "@/lib/api"

/**
 * Composer for one session.
 *
 * While a generation runs the delivery mode is explicit: adjust the current
 * answer (steering) or queue a follow-up. Both become normal history once sent.
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
  const [delivery, setDelivery] = useState<Delivery>("steering")

  function submit() {
    const trimmed = content.trim()
    if (!trimmed || busy) {
      return
    }
    onSend(trimmed, generating ? delivery : undefined)
    setContent("")
  }

  return (
    <div className="border-t p-4">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-2">
        {!llmReady ? (
          <Alert>
            <AlertDescription>
              请先在{" "}
              <Link className="underline" to="/settings">
                模型设置
              </Link>{" "}
              中填写模型信息
            </AlertDescription>
          </Alert>
        ) : null}

        <Textarea
          value={content}
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
          <div className="flex items-center gap-2">
            {generating ? (
              <ToggleGroup
                type="single"
                size="sm"
                variant="outline"
                value={delivery}
                onValueChange={(value) => value && setDelivery(value as Delivery)}
              >
                <ToggleGroupItem value="steering">
                  <CornerDownLeft />
                  调整当前回答
                </ToggleGroupItem>
                <ToggleGroupItem value="follow_up">
                  <Clock />
                  排队追问
                </ToggleGroupItem>
              </ToggleGroup>
            ) : null}
            {pendingCount > 0 && !generating ? (
              <Button size="sm" variant="outline" disabled={busy || !llmReady} onClick={onResume}>
                {busy ? <Spinner data-icon="inline-start" /> : <Clock data-icon="inline-start" />}
                待发送 {pendingCount} 条，继续
              </Button>
            ) : null}
          </div>

          <div className="flex items-center gap-2">
            {generating ? (
              <Button size="sm" variant="destructive" onClick={onStop}>
                <Square data-icon="inline-start" />
                停止
              </Button>
            ) : null}
            <Button size="sm" disabled={busy || !content.trim() || (!generating && !llmReady)} onClick={submit}>
              {busy ? <Spinner data-icon="inline-start" /> : <ArrowUp data-icon="inline-start" />}
              发送
            </Button>
          </div>
        </div>

        {generating ? (
          <Badge variant="outline" className="w-fit">
            生成中
          </Badge>
        ) : null}
      </div>
    </div>
  )
}
