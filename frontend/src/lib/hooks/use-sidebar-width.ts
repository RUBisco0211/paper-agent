import { useCallback, useState } from "react"

const STORAGE_KEY = "paper-agent.sidebar-width"
export const SIDEBAR_MIN_WIDTH = 220
export const SIDEBAR_MAX_WIDTH = 420
export const SIDEBAR_DEFAULT_WIDTH = 264

function clamp(width: number): number {
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, width))
}

/** Sidebar width in pixels, persisted locally (it is a layout preference). */
export function useSidebarWidth() {
  const [width, setWidth] = useState(() => {
    const stored = Number(globalThis.localStorage?.getItem(STORAGE_KEY))
    return Number.isFinite(stored) && stored > 0 ? clamp(stored) : SIDEBAR_DEFAULT_WIDTH
  })

  const update = useCallback((next: number) => {
    const clamped = clamp(next)
    setWidth(clamped)
    try {
      globalThis.localStorage?.setItem(STORAGE_KEY, String(clamped))
    } catch {
      // 存储不可用时仅本次生效
    }
  }, [])

  return { width, setWidth: update }
}
