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
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<AuthStatus>("loading")
  const [user, setUser] = useState<User | null>(null)

  const loadUser = useCallback(async () => {
    const current = await api.auth.me()
    queryClient.clear()
    setUser(current)
    setStatus("authenticated")
  }, [api, queryClient])

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
    },
    [api, queryClient, tokens],
  )

  const register = useCallback(
    async (input: { email: string; password: string; display_name?: string }) => {
      const session = await api.auth.register(input)
      queryClient.clear()
      tokens.set(session)
      setUser(session.user)
      setStatus("authenticated")
    },
    [api, queryClient, tokens],
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
      queryClient.clear()
      setUser(null)
      setStatus("anonymous")
    }
  }, [api, queryClient, tokens])

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
