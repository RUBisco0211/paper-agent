import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { ApiError, type AuthPreferences, type User, type RegisterInput } from "@/lib/api"
import { useApi } from "@/components/providers/ApiProvider"

type AuthStatus = "loading" | "authenticated" | "anonymous"

interface AuthContextValue {
  status: AuthStatus
  user: User | null
  preferences: AuthPreferences | null
  login: (email: string, password: string) => Promise<void>
  register: (input: RegisterInput) => Promise<void>
  logout: () => Promise<void>
  clearSession: () => void
  refreshUser: () => Promise<void>
  setTimezone: (timezone: string) => Promise<void>
  setNotifyEmailDefault: (enabled: boolean) => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const { api, tokens } = useApi()
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<AuthStatus>("loading")
  const [user, setUser] = useState<User | null>(null)
  const [preferences, setPreferences] = useState<AuthPreferences | null>(null)

  /**
   * 首次登录后补一次浏览器时区。
   *
   * 时区是定时任务的执行依据，用户没选过时才用浏览器推断值兜底；已经选过就
   * 不再覆盖，否则换设备登录会把用户自己的选择改掉。
   */
  const loadPreferences = useCallback(async () => {
    const stored = await api.auth.preferences()
    if (stored.timezone) {
      setPreferences(stored)
      return
    }
    const detected = Intl.DateTimeFormat().resolvedOptions().timeZone
    if (!detected) {
      setPreferences(stored)
      return
    }
    try {
      const saved = await api.auth.setTimezone(detected)
      setPreferences({ ...stored, timezone: saved.timezone })
    } catch {
      setPreferences(stored)
      toast.error("无法保存当前时区，定时任务将使用默认时区")
    }
  }, [api])

  const loadUser = useCallback(async () => {
    const current = await api.auth.me()
    queryClient.clear()
    setUser(current)
    setStatus("authenticated")
    await loadPreferences()
  }, [api, queryClient, loadPreferences])

  /**
   * Restore the session from the refresh cookie exactly once.
   *
   * The promise lives in a ref so React StrictMode's double effect invocation
   * shares one bootstrap: a second refresh would replay an already-rotated
   * token, and the backend treats reuse as theft and revokes the whole family.
   * State is applied by the promise itself, not by the effect, so a StrictMode
   * cleanup can never leave the UI stuck on "loading".
   */
  const bootstrapRef = useRef<Promise<void> | null>(null)

  useEffect(() => {
    bootstrapRef.current ??= (async () => {
      try {
        await api.auth.refresh()
        await loadUser()
      } catch {
        tokens.clear()
        queryClient.clear()
        setUser(null)
        setStatus("anonymous")
      }
    })()
  }, [api, loadUser, queryClient, tokens])

  const login = useCallback(
    async (email: string, password: string) => {
      const session = await api.auth.login({ email, password })
      queryClient.clear()
      tokens.set(session)
      setUser(session.user)
      setStatus("authenticated")
      await loadPreferences()
    },
    [api, queryClient, tokens, loadPreferences],
  )

  const register = useCallback(
    async (input: RegisterInput) => {
      const session = await api.auth.register(input)
      queryClient.clear()
      tokens.set(session)
      setUser(session.user)
      setStatus("authenticated")
      await loadPreferences()
    },
    [api, queryClient, tokens, loadPreferences],
  )

  const setTimezone = useCallback(
    async (timezone: string) => {
      const saved = await api.auth.setTimezone(timezone)
      setPreferences((current) => ({ notify_email_default: false, ...current, timezone: saved.timezone }))
    },
    [api],
  )

  const setNotifyEmailDefault = useCallback(
    async (enabled: boolean) => {
      const saved = await api.auth.updatePreferences({ notify_email_default: enabled })
      setPreferences(saved)
    },
    [api],
  )

  const clearSession = useCallback(() => {
    tokens.clear()
    queryClient.clear()
    setUser(null)
    setPreferences(null)
    setStatus("anonymous")
  }, [queryClient, tokens])

  const logout = useCallback(async () => {
    try {
      await api.auth.logout()
    } catch (error) {
      // A failed logout must still clear the local session.
      if (!(error instanceof ApiError)) {
        throw error
      }
    } finally {
      clearSession()
    }
  }, [api, clearSession])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      preferences,
      login,
      register,
      logout,
      clearSession,
      refreshUser: loadUser,
      setTimezone,
      setNotifyEmailDefault,
    }),
    [status, user, preferences, login, register, logout, clearSession, loadUser, setTimezone, setNotifyEmailDefault],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) {
    throw new Error("useAuth 必须在 AuthProvider 内使用")
  }
  return value
}
