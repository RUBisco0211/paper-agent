import type { LlmConfigInput } from "@/lib/api"

/**
 * LLM provider configuration lives in the browser only.
 *
 * The backend accepts `llm_config` per message submission and keeps the key in
 * the running executor's memory: it is never written to the database, logs or
 * object storage. Storing it in localStorage is a deliberate trade-off (an XSS
 * would expose it) and the UI must say so.
 */
const STORAGE_KEY = "paper-agent.llm-config"

export interface StoredLlmConfig extends LlmConfigInput {
  /** Provider base URL is fixed by the backend; only the name is stored. */
  provider: string
}

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

/** Returns the config only when it is complete enough to start a generation. */
export function readyLlmConfig(): StoredLlmConfig | null {
  const config = loadLlmConfig()
  if (!config) {
    return null
  }
  const complete = Boolean(
    config.provider.trim() && config.model.trim() && config.api_key.trim(),
  )
  return complete ? config : null
}

function safeStorage(): Storage | null {
  try {
    return globalThis.localStorage ?? null
  } catch {
    // Storage can be unavailable (private mode, embedded webview).
    return null
  }
}
