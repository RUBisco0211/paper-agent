import { createContext, useContext, useState, type ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { useApi } from "@/lib/api/provider"
import type { ImportQueueItem } from "@/lib/api/types"

interface ImportQueueState {
  open: boolean
  setOpen: (open: boolean) => void
  items: ImportQueueItem[]
  loading: boolean
  error: boolean
  active: boolean
}
const ImportQueueContext = createContext<ImportQueueState>({ open: false, setOpen: () => undefined, items: [], loading: false, error: false, active: false })

export function ImportQueueProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const { api } = useApi()
  const queue = useQuery({ queryKey: ["import-queue"], queryFn: api.imports.queue, refetchInterval: 3000 })
  const items = queue.data?.items ?? []
  const active = items.some((item) => ["queued", "running", "resolving", "downloading", "metadata_ready"].includes(item.status))
  return <ImportQueueContext.Provider value={{ open, setOpen, items, loading: queue.isLoading, error: queue.isError, active }}>{children}</ImportQueueContext.Provider>
}

export function useImportQueue() {
  return useContext(ImportQueueContext)
}
