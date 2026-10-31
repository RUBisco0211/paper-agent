import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react"

export const THEMES = [
  { id: "vintage-paper", label: "暖纸" },
  { id: "solar-dusk", label: "暮沙" },
  { id: "smui", label: "蓝灰" },
] as const

export type ThemeId = (typeof THEMES)[number]["id"]

const STORAGE_KEY = "paper-agent.theme"
const DEFAULT_THEME: ThemeId = "vintage-paper"

function isTheme(value: string | null): value is ThemeId {
  return THEMES.some((theme) => theme.id === value)
}

/** 浏览器里就是 localStorage；测试环境的 Node 全局同名实现不可用，按 window 取。 */
function storage(): Storage | null {
  try {
    return globalThis.window?.localStorage ?? null
  } catch {
    return null
  }
}

/** 读 localStorage 的主题；首帧前的脚本与这里读同一个键。 */
export function loadTheme(): ThemeId {
  try {
    const stored = storage()?.getItem(STORAGE_KEY) ?? null
    return isTheme(stored) ? stored : DEFAULT_THEME
  } catch {
    return DEFAULT_THEME
  }
}

function applyTheme(theme: ThemeId) {
  // 默认主题没有 data-theme 规则，等于回落到 index.css 里的那一套。
  if (theme === DEFAULT_THEME) delete document.documentElement.dataset.theme
  else document.documentElement.dataset.theme = theme
}

const ThemeContext = createContext<{ theme: ThemeId; setTheme: (theme: ThemeId) => void } | null>(null)

/**
 * Applies the user's colour theme and keeps the OS light/dark class in sync.
 *
 * The theme itself is a local preference: it never leaves the browser, so it
 * lives in localStorage rather than in the account settings.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeId>(loadTheme)

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)")
    const apply = () => {
      document.documentElement.classList.toggle("dark", query.matches)
    }
    apply()
    query.addEventListener("change", apply)
    return () => query.removeEventListener("change", apply)
  }, [])

  const setTheme = useCallback((next: ThemeId) => {
    try {
      storage()?.setItem(STORAGE_KEY, next)
    } catch {
      // 存不了也不影响本次切换，下次回到默认主题。
    }
    setThemeState(next)
  }, [])

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const value = useContext(ThemeContext)
  if (!value) throw new Error("useTheme 必须在 ThemeProvider 内使用")
  return value
}
