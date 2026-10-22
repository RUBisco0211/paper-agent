import { useQuery } from "@tanstack/react-query"
import { KeyRound, Plus } from "lucide-react"
import { useState } from "react"

import { useApi } from "@/components/providers/ApiProvider"
import { credentialApi } from "@/lib/api/agentscope/credential"
import { Button } from "@/components/ui/Button"
import { Input } from "@/components/ui/Input"
import { Sidebar, SidebarContent, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/Sidebar"

export function ModelsSection() {
  const { api } = useApi()
  const catalog = useQuery({ queryKey: ["llm-catalog"], queryFn: api.sessions.llmCatalog })
  const credentials = useQuery({ queryKey: ["credentials"], queryFn: credentialApi.list })
  const [provider, setProvider] = useState("")
  const [key, setKey] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState(false)
  const selected = provider || catalog.data?.providers[0]?.id || ""
  const chosen = catalog.data?.providers.find((item) => item.id === selected)
  const saved = credentials.data?.credentials.filter((item) => item.data.type === `${selected}_credential`) ?? []

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

  return <div className="flex h-full w-full">
    <Sidebar collapsible="none" className="border-r">
      <SidebarContent><SidebarGroup><SidebarGroupLabel>提供商</SidebarGroupLabel><SidebarGroupContent><SidebarMenu>
        {catalog.data?.providers.map((item) => <SidebarMenuItem key={item.id}>
          <SidebarMenuButton isActive={selected === item.id} onClick={() => { setProvider(item.id); setError(""); setSuccess(false) }}><KeyRound />{item.label}</SidebarMenuButton>
        </SidebarMenuItem>)}
      </SidebarMenu></SidebarGroupContent></SidebarGroup></SidebarContent>
    </Sidebar>
    <div className="min-w-0 flex-1 overflow-y-auto">
    <div className="mx-auto max-w-3xl space-y-8">
      <section className="space-y-4"><h2 className="text-base font-medium">已保存的凭据</h2>
        {credentials.isPending && <p className="text-sm text-muted-foreground">加载中…</p>}
        {saved.length === 0 && !credentials.isPending && <p className="text-sm text-muted-foreground">尚未配置</p>}
        {saved.map((item) => <div key={item.id} className="flex items-center justify-between rounded-lg border px-4 py-3 text-sm"><span>{String(item.data.name ?? chosen?.label ?? "凭据")}</span><span className="text-muted-foreground">密钥已隐藏</span></div>)}
      </section>
      <section className="rounded-lg border p-5"><h2 className="mb-4 flex items-center gap-2 font-medium"><Plus className="size-4" />保存凭据</h2>
        <form onSubmit={(event) => void save(event)} className="space-y-4">
          <label htmlFor="provider-key" className="block text-sm">API Key</label>
          <Input id="provider-key" type="password" autoComplete="off" value={key} onChange={(event) => setKey(event.target.value)} />
          <Button type="submit" disabled={saving || !selected || !key.trim()}>{saving ? "保存中…" : "保存凭据"}</Button>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          {success && <p role="status" className="text-sm">凭据已保存</p>}
        </form>
      </section>
    </div>
    </div>
  </div>
}
