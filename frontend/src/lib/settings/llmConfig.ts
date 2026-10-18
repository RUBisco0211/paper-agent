import type { LlmConfigInput } from "@/lib/api"

const STORAGE_KEY = "paper-agent.llm-config"

export type StoredLlmConfig = LlmConfigInput

export function loadLlmConfig(): StoredLlmConfig | null {
  const raw = safeStorage()?.getItem(STORAGE_KEY)
  if (!raw) {
    return null
  }
  try {
    const parsed = JSON.parse(raw) as Partial<StoredLlmConfig>
    if (!parsed.provider || !parsed.model || !parsed.api_key) {
      return null
    }
    return {
      provider: parsed.provider,
      model: parsed.model,
      api_key: parsed.api_key,
      reasoning_effort: parsed.reasoning_effort,
    }
  } catch {
    return null
  }
}

export function saveLlmConfig(config: StoredLlmConfig): void {
  safeStorage()?.setItem(STORAGE_KEY, JSON.stringify(config))
}

export function clearLlmConfig(): void {
  safeStorage()?.removeItem(STORAGE_KEY)
}

function safeStorage(): Storage | null {
  try {
    return globalThis.localStorage ?? null
  } catch {
    return null
  }
}
