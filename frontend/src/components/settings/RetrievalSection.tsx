import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { KeyRound, Waypoints } from "lucide-react"
import { useState } from "react"

import { useApi } from "@/components/providers/ApiProvider"
import { Button } from "@/components/ui/Button"
import { Input } from "@/components/ui/Input"

const KIND = "embedding"

/**
 * The user's own key for search-time query vectors.
 *
 * Ingestion vectors are produced by the deployment and shared, so ingesting a
 * paper costs the user nothing. Every search embeds the question with this key,
 * which is why the quota and rate limit belong to whoever is asking.
 */
export function RetrievalSection() {
  const { api } = useApi()
  const queryClient = useQueryClient()
  const credentials = useQuery({
    queryKey: ["service-credentials"],
    queryFn: api.serviceCredentials.list,
  })
  const [key, setKey] = useState("")
  const [error, setError] = useState("")
  const [success, setSuccess] = useState(false)

  const saved = credentials.data?.items.find((item) => item.kind === KIND)

  const save = useMutation({
    mutationFn: (value: string) =>
      api.serviceCredentials.save(KIND, { label: "Embedding", fields: { api_key: value } }),
    onSuccess: async () => {
      setKey("")
      setSuccess(true)
      setError("")
      await queryClient.invalidateQueries({ queryKey: ["service-credentials"] })
    },
    onError: (cause) => {
      setSuccess(false)
      setError(cause instanceof Error ? cause.message : "保存失败")
    },
  })

  const remove = useMutation({
    mutationFn: () => api.serviceCredentials.remove(KIND),
    onSuccess: async () => {
      setSuccess(false)
      setError("")
      await queryClient.invalidateQueries({ queryKey: ["service-credentials"] })
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : "移除失败"),
  })

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <section className="space-y-2">
        <h2 className="flex items-center gap-2 text-base font-medium">
          <Waypoints className="size-4" />
          向量检索
        </h2>
        <p className="text-sm text-muted-foreground">
          检索时用你的密钥把问题转成向量，再与文献片段比对。文献入库时的向量由本站承担，不消耗你的额度。未配置时仍可只用关键词检索，但不会做语义匹配。
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-base font-medium">已保存的密钥</h2>
        {credentials.isPending && <p className="text-sm text-muted-foreground">加载中…</p>}
        {!credentials.isPending && !saved && (
          <p className="text-sm text-muted-foreground">尚未配置</p>
        )}
        {saved && (
          <div className="flex items-center justify-between rounded-lg border px-4 py-3 text-sm">
            <span className="flex items-center gap-2">
              <KeyRound className="size-4" />
              {saved.label || "Embedding"}
            </span>
            <span className="flex items-center gap-3 text-muted-foreground">
              密钥已隐藏
              <Button
                type="button"
                variant="outline"
                disabled={remove.isPending}
                onClick={() => remove.mutate()}
              >
                移除
              </Button>
            </span>
          </div>
        )}
      </section>

      <section className="rounded-lg border p-5">
        <h2 className="mb-4 font-medium">{saved ? "更换密钥" : "保存密钥"}</h2>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (!key.trim()) return
            save.mutate(key.trim())
          }}
        >
          <label htmlFor="embedding-key" className="block text-sm">
            Embedding API Key
          </label>
          <Input
            id="embedding-key"
            type="password"
            autoComplete="off"
            value={key}
            onChange={(event) => {
              setKey(event.target.value)
              setSuccess(false)
            }}
          />
          <p className="text-xs text-muted-foreground">
            密钥保存在你自己的账户下，仅用于把你的检索问题转成向量。
          </p>
          <Button type="submit" disabled={save.isPending || !key.trim()}>
            {save.isPending ? "保存中…" : "保存密钥"}
          </Button>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          {success && (
            <p role="status" className="text-sm">
              密钥已保存
            </p>
          )}
        </form>
      </section>
    </div>
  )
}
