import { useQuery } from "@tanstack/react-query"
import { KeyRound } from "lucide-react"
import { useEffect, useMemo, useState } from "react"

import { PageHeader } from "@/app/app-shell"
import { queryKeys } from "@/app/query"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { useApi } from "@/lib/api/provider"
import { notifySuccess } from "@/lib/errors"
import { useLlmConfig } from "@/lib/settings/llm-config-hooks"

export function SettingsPage() {
  const { api } = useApi()
  const { config, save, clear } = useLlmConfig()
  const [provider, setProvider] = useState(config?.provider ?? "")
  const [model, setModel] = useState(config?.model ?? "")
  const [apiKey, setApiKey] = useState(config?.api_key ?? "")

  const catalog = useQuery({
    queryKey: queryKeys.llmCatalog,
    queryFn: () => api.sessions.llmCatalog(),
  })
  const providers = catalog.data?.providers ?? []
  const selectedProvider = providers.find((item) => item.id === provider)
  const models = useMemo(() => selectedProvider?.models ?? [], [selectedProvider])
  const selectedModel = models.find((item) => item.id === model)

  useEffect(() => {
    if (providers.length === 0) {
      return
    }
    const nextProvider = providers.find((item) => item.id === provider) ?? providers[0]
    const nextModel =
      nextProvider.models.find((item) => item.id === model) ?? nextProvider.models[0]
    if (nextProvider.id !== provider) {
      setProvider(nextProvider.id)
    }
    if (nextModel && nextModel.id !== model) {
      setModel(nextModel.id)
    }
  }, [model, provider, providers])

  function selectProvider(next: string) {
    setProvider(next)
    const firstModel = providers.find((item) => item.id === next)?.models[0]
    setModel(firstModel?.id ?? "")
  }

  function handleSave(event: React.FormEvent) {
    event.preventDefault()
    save({ provider, model, api_key: apiKey.trim() })
    notifySuccess("已保存")
  }

  const canSave = Boolean(provider && model && apiKey.trim())

  return (
    <>
      <PageHeader title="设置" />
      <div className="max-w-xl p-4 md:p-6">
        <Card>
          <CardHeader>
            <CardTitle>问答模型</CardTitle>
          </CardHeader>
          <CardContent>
            {catalog.isError ? (
              <Alert variant="destructive" className="mb-4">
                <AlertDescription>暂时无法读取模型列表，请稍后重试。</AlertDescription>
              </Alert>
            ) : null}
            <form className="flex flex-col gap-4" onSubmit={handleSave}>
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="provider">提供商</FieldLabel>
                  <Select
                    value={provider}
                    onValueChange={selectProvider}
                    disabled={catalog.isPending}
                  >
                    <SelectTrigger id="provider" className="w-full">
                      <SelectValue placeholder="选择提供商" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {providers.map((item) => (
                          <SelectItem key={item.id} value={item.id}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </Field>

                <Field>
                  <FieldLabel htmlFor="model">模型</FieldLabel>
                  <Select value={model} onValueChange={setModel} disabled={!selectedProvider}>
                    <SelectTrigger id="model" className="w-full">
                      <SelectValue placeholder="选择模型" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {models.map((item) => (
                          <SelectItem key={item.id} value={item.id}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                  {selectedModel?.context_size ? (
                    <FieldDescription>
                      上下文长度 {selectedModel.context_size.toLocaleString()} tokens
                    </FieldDescription>
                  ) : null}
                </Field>

                <Field>
                  <FieldLabel htmlFor="api_key">API Key</FieldLabel>
                  <InputGroup>
                    <InputGroupAddon>
                      <KeyRound />
                    </InputGroupAddon>
                    <InputGroupInput
                      id="api_key"
                      type="password"
                      autoComplete="off"
                      value={apiKey}
                      placeholder="sk-…"
                      onChange={(event) => setApiKey(event.target.value)}
                    />
                  </InputGroup>
                </Field>
              </FieldGroup>

              <div className="flex items-center gap-2">
                <Button type="submit" disabled={!canSave || catalog.isPending}>
                  {catalog.isPending ? <Spinner data-icon="inline-start" /> : null}
                  保存
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    clear()
                    setApiKey("")
                  }}
                >
                  清除密钥
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </>
  )
}
