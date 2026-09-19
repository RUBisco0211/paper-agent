import { ArrowUp, Brain, Check, ChevronDown, Clock, CornerDownLeft, Paperclip, Square } from "lucide-react"
import { useRef, useState } from "react"
import { Link } from "react-router-dom"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Attachment, AttachmentContent, AttachmentIcon, AttachmentRemove } from "@/components/ui/attachment"
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupTextarea } from "@/components/ui/input-group"
import { Spinner } from "@/components/ui/spinner"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import type { Delivery, LlmConfigInput, LlmProviderOption, SessionScope } from "@/lib/api"

const EFFORT_LABEL: Record<string, string> = {
  none: "关闭", minimal: "最低", low: "低", medium: "中", high: "高", xhigh: "很高", max: "最高",
}

interface UploadedFile { id: string; name: string; pending: boolean; detail: string }

export function Composer({
  generating, pendingCount, llmReady, busy, config, providers = [], scope = "library",
  onConfigChange, onAttach, onSend, onStop, onResume,
}: {
  generating: boolean
  pendingCount: number
  llmReady: boolean
  busy: boolean
  config?: LlmConfigInput | null
  providers?: LlmProviderOption[]
  scope?: SessionScope
  onConfigChange?: (config: LlmConfigInput) => void
  onAttach?: (file: File) => Promise<void>
  onSend: (content: string, delivery?: Delivery) => void
  onStop: () => void
  onResume: () => void
}) {
  const [content, setContent] = useState("")
  const [delivery, setDelivery] = useState<Delivery>("steering")
  const [files, setFiles] = useState<UploadedFile[]>([])
  const fileInput = useRef<HTMLInputElement>(null)
  const provider = providers.find((item) => item.id === config?.provider)
  const model = provider?.models.find((item) => item.id === config?.model)
  const effort = config?.reasoning_effort
  const canAttach = scope !== "paper" && Boolean(onAttach)

  function submit() {
    const trimmed = content.trim()
    if (!trimmed || busy || (!generating && !llmReady)) return
    onSend(trimmed, generating ? delivery : undefined)
    setContent("")
  }

  function changeModel(modelId: string) {
    if (!config || !onConfigChange) return
    onConfigChange({ ...config, model: modelId, reasoning_effort: undefined })
  }

  function changeEffort(value: string) {
    if (!config || !onConfigChange) return
    onConfigChange({ ...config, reasoning_effort: value === "default" ? undefined : value })
  }

  async function attach(file: File) {
    if (!onAttach) return
    const id = `${file.name}-${file.lastModified}`
    setFiles((current) => [...current, { id, name: file.name, pending: true, detail: "正在上传…" }])
    try {
      await onAttach(file)
      setFiles((current) => current.map((item) => item.id === id
        ? { ...item, pending: false, detail: "已加入当前范围，正在解析" }
        : item))
    } catch {
      setFiles((current) => current.filter((item) => item.id !== id))
    }
  }

  return (
    <div className="bg-background/95 border-t p-4 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <form className="mx-auto w-full max-w-3xl" onSubmit={(event) => { event.preventDefault(); submit() }}>
        {!llmReady ? (
          <Alert className="mb-3"><AlertDescription>
            请选择问答模型并填写 API Key。 <Link className="underline" to="/settings">前往设置</Link>
          </AlertDescription></Alert>
        ) : null}
        <InputGroup className="rounded-xl">
          {files.length > 0 ? (
            <InputGroupAddon align="block-start" className="flex-wrap">
              {files.map((file) => (
                <Attachment key={file.id} className="max-w-72">
                  <AttachmentIcon pending={file.pending} />
                  <AttachmentContent name={file.name} detail={file.detail} />
                  {!file.pending ? <AttachmentRemove onClick={() => setFiles((current) => current.filter((item) => item.id !== file.id))} /> : null}
                </Attachment>
              ))}
            </InputGroupAddon>
          ) : null}
          <InputGroupTextarea
            aria-label="消息" value={content} rows={3}
            className="max-h-48 min-h-24 px-4" onChange={(event) => setContent(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); submit() } }}
          />
          <InputGroupAddon align="block-end" className="justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-1">
              <input
                ref={fileInput} className="sr-only" type="file" accept="application/pdf,.pdf" aria-label="选择 PDF"
                onChange={(event) => { const file = event.target.files?.[0]; if (file) void attach(file); event.target.value = "" }}
              />
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <InputGroupButton size="icon-sm" variant="ghost" aria-label="添加 PDF" disabled={!canAttach} onClick={() => fileInput.current?.click()}>
                      <Paperclip />
                    </InputGroupButton>
                  </TooltipTrigger>
                  <TooltipContent>{scope === "paper" ? "单篇论文会话不能扩展文献范围" : "添加 PDF 到当前范围"}</TooltipContent>
                </Tooltip>
              </TooltipProvider>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <InputGroupButton size="sm" variant="ghost" disabled={!config || !provider}>
                    <span className="max-w-40 truncate">{model?.label ?? config?.model ?? "选择模型"}</span>
                    <ChevronDown data-icon="inline-end" />
                  </InputGroupButton>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="min-w-64">
                  <DropdownMenuLabel>{provider?.label ?? "模型"}</DropdownMenuLabel>
                  <DropdownMenuGroup>
                    {provider?.models.map((item) => (
                      <DropdownMenuItem key={item.id} onSelect={() => changeModel(item.id)}>
                        {item.id === model?.id ? <Check /> : null}<span className="truncate">{item.label}</span>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuGroup>
                  <DropdownMenuSeparator />
                  <DropdownMenuGroup><DropdownMenuItem asChild><Link to="/settings">更换提供商或 API Key</Link></DropdownMenuItem></DropdownMenuGroup>
                </DropdownMenuContent>
              </DropdownMenu>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <InputGroupButton size="sm" variant="ghost" disabled={!model}>
                    <Brain data-icon="inline-start" />
                    {effort ? `思考 ${EFFORT_LABEL[effort] ?? effort}` : "思考 默认"}
                    <ChevronDown data-icon="inline-end" />
                  </InputGroupButton>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  <DropdownMenuLabel>思考强度</DropdownMenuLabel>
                  <DropdownMenuRadioGroup value={effort ?? "default"} onValueChange={changeEffort}>
                    <DropdownMenuRadioItem value="default">模型默认</DropdownMenuRadioItem>
                    {model?.reasoning_efforts.map((value) => <DropdownMenuRadioItem key={value} value={value}>{EFFORT_LABEL[value] ?? value}</DropdownMenuRadioItem>)}
                  </DropdownMenuRadioGroup>
                  {model?.reasoning_efforts.length === 0 ? <><DropdownMenuSeparator /><DropdownMenuLabel className="text-muted-foreground font-normal">此模型没有可调档位</DropdownMenuLabel></> : null}
                </DropdownMenuContent>
              </DropdownMenu>

              {generating ? (
                <ToggleGroup type="single" size="sm" variant="outline" value={delivery} onValueChange={(value) => value && setDelivery(value as Delivery)}>
                  <ToggleGroupItem value="steering"><CornerDownLeft />调整当前回答</ToggleGroupItem>
                  <ToggleGroupItem value="follow_up"><Clock />排队追问</ToggleGroupItem>
                </ToggleGroup>
              ) : null}
              {pendingCount > 0 && !generating ? (
                <InputGroupButton size="sm" variant="outline" disabled={busy || !llmReady} onClick={onResume}>
                  {busy ? <Spinner data-icon="inline-start" /> : <Clock data-icon="inline-start" />}待发送 {pendingCount} 条
                </InputGroupButton>
              ) : null}
            </div>
            <div className="ml-auto flex items-center gap-1">
              {generating ? <InputGroupButton size="icon-sm" variant="ghost" aria-label="停止" disabled={busy} onClick={onStop}><Square /></InputGroupButton> : null}
              <InputGroupButton type="submit" size="icon-sm" variant="default" aria-label="发送" disabled={busy || !content.trim() || (!generating && !llmReady)}>
                {busy ? <Spinner /> : <ArrowUp />}
              </InputGroupButton>
            </div>
          </InputGroupAddon>
        </InputGroup>
      </form>
    </div>
  )
}
