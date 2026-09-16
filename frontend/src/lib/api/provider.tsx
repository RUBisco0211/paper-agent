import { createContext, useContext, useMemo, type ReactNode } from "react"

import { AccessTokenStore } from "@/lib/auth/token-store"
import { createApi, type Api, type ApiClientOptions } from "@/lib/api"

interface ApiContextValue {
  api: Api
  tokens: AccessTokenStore
}

const ApiContext = createContext<ApiContextValue | null>(null)

export function ApiProvider({
  children,
  options,
}: {
  children: ReactNode
  options?: Omit<ApiClientOptions, "getAccessToken" | "onAccessToken">
}) {
  const value = useMemo<ApiContextValue>(() => {
    const tokens = new AccessTokenStore()
    const api = createApi({ ...options, ...tokens.clientOptions })
    return { api, tokens }
  }, [options])

  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>
}

export function useApi(): ApiContextValue {
  const value = useContext(ApiContext)
  if (!value) {
    throw new Error("useApi 必须在 ApiProvider 内使用")
  }
  return value
}
