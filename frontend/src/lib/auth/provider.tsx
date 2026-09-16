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

import { ApiError, type User } from "@/lib/api"
import { useApi } from "@/lib/api/provider"

type AuthStatus = "loading" | "authenticated" | "anonymous"

interface AuthContextValue {
  status: AuthStatus
  user: User | null
  login: (email: string, password: string) => Promise<void>
  register: (input: {
    email: string
    password: string
    display_name?: string
  }) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const { api, tokens } = useApi()
  const [status, setStatus] = useState<AuthStatus>("loading")
  const [user, setUser] = useState<User | null>(null)
  const bootstrapped = useRef(false)

  const loadUser = useCallback(async () => {
    const current = await api.auth.me()
    setUser(current)
    setStatus("authenticated")
  }, [api])

  /**
   * A hard reload has no access token: restore the session from the refresh
   * cookie before deciding the visitor is anonymous.
   */
  useEffect(() => {
    if (bootstrapped.current) {
      return
    }
    bootstrapped.current = true
    let cancelled = false
    void (async () => {
      try {
        await api.auth.refresh()
        if (!cancelled) {
          await loadUser()
        }
      } catch {
        if (!cancelled) {
          tokens.clear()
          setUser(null)
          setStatus("anonymous")
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [api, loadUser, tokens])

  const login = useCallback(
    async (email: string, password: string) => {
      const session = await api.auth.login({ email, password })
      tokens.set(session)
      setUser(session.user)
      setStatus("authenticated")
    },
    [api, tokens],
  )

  const register = useCallback(
    async (input: { email: string; password: string; display_name?: string }) => {
      const session = await api.auth.register(input)
      tokens.set(session)
      setUser(session.user)
      setStatus("authenticated")
    },
    [api, tokens],
  )

  const logout = useCallback(async () => {
    try {
      await api.auth.logout()
    } catch (error) {
      // A failed logout must still clear the local session.
      if (!(error instanceof ApiError)) {
        throw error
      }
    } finally {
      tokens.clear()
      setUser(null)
      setStatus("anonymous")
    }
  }, [api, tokens])

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, login, register, logout, refreshUser: loadUser }),
    [status, user, login, register, logout, loadUser],
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
