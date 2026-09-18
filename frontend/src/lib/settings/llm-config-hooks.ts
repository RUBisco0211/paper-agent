import { useCallback, useEffect, useState } from "react"

import {
  clearLlmConfig,
  loadLlmConfig,
  saveLlmConfig,
  type StoredLlmConfig,
} from "@/lib/settings/llm-config"

export function useLlmConfig() {
  const [config, setConfig] = useState<StoredLlmConfig | null>(() => loadLlmConfig())

  useEffect(() => {
    setConfig(loadLlmConfig())
  }, [])

  const save = useCallback((next: StoredLlmConfig) => {
    saveLlmConfig(next)
    setConfig(next)
  }, [])

  const clear = useCallback(() => {
    clearLlmConfig()
    setConfig(null)
  }, [])

  const isReady = Boolean(
    config?.provider?.trim() && config?.model?.trim() && config?.api_key?.trim(),
  )

  return { config, save, clear, isReady }
}
