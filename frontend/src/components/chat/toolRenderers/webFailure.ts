/**
 * A web tool reports failure as an ordinary result carrying a stable code.
 * The UI shows the code itself rather than the message: the message is written
 * for the agent, and the code is the part both sides agree on.
 */
const FALLBACK = "provider_unavailable"

export function readFailureCode(text: string): string | null {
  try {
    const data: unknown = JSON.parse(text)
    if (!data || typeof data !== "object") return null
    const { status, code } = data as { status?: unknown; code?: unknown }
    if (status !== "error") return null
    return typeof code === "string" && code ? code : FALLBACK
  } catch {
    return null
  }
}
