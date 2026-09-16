import { useState } from "react"

import { PageHeader } from "@/app/app-shell"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ALLOWED_PROVIDERS, useLlmConfig } from "@/lib/settings/llm-config-hooks"
import { notifySuccess } from "@/lib/errors"

export function SettingsPage() {
  const { config, save, clear, isReady } = useLlmConfig()
  const [provider, setProvider] = useState(config?.provider ?? "openai")
  const [model, setModel] = useState(config?.model ?? "")
  const [apiKey, setApiKey] = useState(config?.api_key ?? "")

  function handleSave(event: React.FormEvent) {
    event.preventDefault()
    save({ provider, model: model.trim(), api_key: apiKey.trim() })
    notifySuccess("已保存到本机浏览器", "提交消息时会作为瞬时配置发给后端")
  }

  return (
    <>
      <PageHeader
        title="模型设置"
        description="选择允许的 Provider 并填写模型与 API Key；配置只保存在本机浏览器。"
      />
      <div className="flex max-w-2xl flex-col gap-4 p-6">
        <Alert>
          <AlertTitle>API Key 的存放位置</AlertTitle>
          <AlertDescription>
            Key 保存在浏览器 localStorage，提交消息时通过请求体传给后端，仅驻留执行器内存：
            不写入数据库、日志或对象存储。共享电脑上请不要保存。
          </AlertDescription>
        </Alert>
        <Card>
          <CardHeader>
            <CardTitle>Provider 配置</CardTitle>
            <CardDescription>
              Base URL 由后端部署配置固定，前端只能选择 Provider 名称。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="flex flex-col gap-4" onSubmit={handleSave}>
              <div className="flex flex-col gap-2">
                <Label htmlFor="provider">Provider</Label>
                <Select value={provider} onValueChange={setProvider}>
                  <SelectTrigger id="provider" className="w-full">
                    <SelectValue placeholder="选择 Provider" />
                  </SelectTrigger>
                  <SelectContent>
                    {ALLOWED_PROVIDERS.map((item) => (
                      <SelectItem key={item} value={item}>
                        {item}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="model">模型</Label>
                <Input
                  id="model"
                  value={model}
                  placeholder="例如 gpt-4o-mini"
                  onChange={(event) => setModel(event.target.value)}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="api_key">API Key</Label>
                <Input
                  id="api_key"
                  type="password"
                  value={apiKey}
                  placeholder="sk-…"
                  onChange={(event) => setApiKey(event.target.value)}
                />
              </div>
              <div className="flex items-center gap-2">
                <Button type="submit">保存</Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    clear()
                    setModel("")
                    setApiKey("")
                  }}
                >
                  清除
                </Button>
                <span className="text-muted-foreground text-xs">
                  {isReady ? "配置完整，可以开始问答" : "配置不完整，尚不能发起生成"}
                </span>
              </div>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>数据流向</CardTitle>
          </CardHeader>
          <CardContent className="text-muted-foreground flex flex-col gap-1 text-sm">
            <p>· PDF 会发往部署者配置的 MinerU 解析服务；</p>
            <p>· Chunk 文本会发往实例级 Embedding 服务生成向量；</p>
            <p>· 你的问题与检索到的论文证据会发往上面选择的 LLM Provider。</p>
          </CardContent>
        </Card>
      </div>
    </>
  )
}
