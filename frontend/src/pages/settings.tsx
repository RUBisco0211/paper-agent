import { useState } from "react"

import { PageHeader } from "@/app/app-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { notifySuccess } from "@/lib/errors"
import { ALLOWED_PROVIDERS, useLlmConfig } from "@/lib/settings/llm-config-hooks"

export function SettingsPage() {
  const { config, save, clear } = useLlmConfig()
  const [provider, setProvider] = useState(config?.provider ?? "openai")
  const [model, setModel] = useState(config?.model ?? "")
  const [apiKey, setApiKey] = useState(config?.api_key ?? "")
  const [saving, setSaving] = useState(false)

  function handleSave(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    save({ provider, model: model.trim(), api_key: apiKey.trim() })
    setSaving(false)
    notifySuccess("已保存")
  }

  return (
    <>
      <PageHeader title="模型设置" />
      <div className="max-w-xl p-4">
        <Card>
          <CardHeader>
            <CardTitle>模型</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="flex flex-col gap-4" onSubmit={handleSave}>
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="provider">Provider</FieldLabel>
                  <Select value={provider} onValueChange={setProvider}>
                    <SelectTrigger id="provider" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {ALLOWED_PROVIDERS.map((item) => (
                          <SelectItem key={item} value={item}>
                            {item}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </Field>
                <Field>
                  <FieldLabel htmlFor="model">模型</FieldLabel>
                  <Input
                    id="model"
                    value={model}
                    placeholder="gpt-4o-mini"
                    onChange={(event) => setModel(event.target.value)}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="api_key">API Key</FieldLabel>
                  <Input
                    id="api_key"
                    type="password"
                    value={apiKey}
                    placeholder="sk-…"
                    onChange={(event) => setApiKey(event.target.value)}
                  />
                </Field>
              </FieldGroup>
              <div className="flex items-center gap-2">
                <Button type="submit" disabled={saving}>
                  {saving ? <Spinner data-icon="inline-start" /> : null}
                  保存
                </Button>
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
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </>
  )
}
