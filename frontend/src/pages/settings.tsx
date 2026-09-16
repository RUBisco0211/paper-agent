import { useState } from "react"

import { PageHeader } from "@/app/app-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
    notifySuccess("已保存")
  }

  return (
    <>
      <PageHeader
        title="模型设置"
      />
      <div className="flex max-w-2xl flex-col gap-4 p-6">
        <Card>
          <CardHeader>
            <CardTitle>模型</CardTitle>
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
      </div>
    </>
  )
}
