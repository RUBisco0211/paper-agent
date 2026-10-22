/**
 * A web tool reports failure as an ordinary result rather than an exception.
 * The UI does not distinguish the reasons: one error line covers them all.
 */
export function isFailure(text: string): boolean {
  try {
    const data: unknown = JSON.parse(text)
    if (!data || typeof data !== "object") return false
    return (data as { status?: unknown }).status === "error"
  } catch {
    return false
  }
}

/** One line for every failure, whatever the underlying code was. */
export function WebToolError() {
  return (
    <p role="alert" className="p-3 text-sm text-destructive">
      工具调用错误
    </p>
  )
}
