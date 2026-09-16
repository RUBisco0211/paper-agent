import { Navigate, useLocation } from "react-router-dom"

import { useAuth } from "@/lib/auth/provider"

/** Waits for the session bootstrap before deciding to redirect. */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status } = useAuth()
  const location = useLocation()

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground text-sm">正在恢复登录态…</p>
      </div>
    )
  }
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <>{children}</>
}
