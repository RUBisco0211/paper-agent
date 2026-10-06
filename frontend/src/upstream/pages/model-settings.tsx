import { useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { useApi } from "@/lib/api/provider"
import { credentialApi } from "@upstream/api/credential"
import { Button } from "@upstream/components/ui/button"
import { Input } from "@upstream/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@upstream/components/ui/select"

export function ModelSettingsPage() {
  const { api } = useApi()
  const catalog = useQuery({ queryKey: ["llm-catalog"], queryFn: api.sessions.llmCatalog })
  const credentials = useQuery({ queryKey: ["credentials"], queryFn: credentialApi.list })
  const [provider, setProvider] = useState("")
  const [key, setKey] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState(false)
  const selected = provider || catalog.data?.providers[0]?.id || ""

  async function save(event: React.FormEvent) {
    event.preventDefault()
    if (!selected || !key.trim()) return
    setSaving(true)
    setError("")
    setSuccess(false)
    try {
      await credentialApi.create({ data: { type: `${selected}_credential`, api_key: key.trim() } })
      setKey("")
      setSuccess(true)
      await credentials.refetch()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="h-full overflow-auto p-6 md:p-10">
      <div className="mx-auto max-w-xl space-y-7">
        <h1 className="text-2xl font-semibold">模型设置</h1>
        <form onSubmit={(event) => void save(event)} className="space-y-5 rounded-2xl border bg-card p-6">
          <label className="block space-y-2 text-sm font-medium">提供商
            <Select value={selected} onValueChange={setProvider}>
              <SelectTrigger className="mt-2 w-full"><SelectValue placeholder="选择提供商" /></SelectTrigger>
              <SelectContent>{catalog.data?.providers.map((item) => <SelectItem key={item.id} value={item.id}>{item.label}</SelectItem>)}</SelectContent>
            </Select>
          </label>
          <label className="block space-y-2 text-sm font-medium">API Key
            <Input className="mt-2" type="password" autoComplete="off" value={key} onChange={(event) => setKey(event.target.value)} />
          </label>
          <Button type="submit" disabled={saving || !selected || !key.trim()}>{saving ? "保存中…" : "保存凭据"}</Button>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          {success && <p role="status" className="text-sm">凭据已保存</p>}
        </form>
        <section className="space-y-3"><h2 className="font-medium">已保存的凭据</h2>
          {credentials.data?.credentials.length === 0 && <p className="text-sm text-muted-foreground">尚未配置</p>}
          {credentials.data?.credentials.map((item) => <div key={item.id} className="flex items-center justify-between rounded-xl border bg-card px-4 py-3 text-sm"><span>{String(item.data.name ?? item.data.type ?? "凭据")}</span><span className="text-muted-foreground">密钥已隐藏</span></div>)}
        </section>
      </div>
    </main>
  )
}
