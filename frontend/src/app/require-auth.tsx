import { Navigate, useLocation } from "react-router-dom"

import { Spinner } from "@/components/ui/spinner"
import { useAuth } from "@/lib/auth/provider"

/** Waits for the session bootstrap before deciding to redirect. */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status } = useAuth()
  const location = useLocation()

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner className="text-muted-foreground size-5" />
      </div>
    )
  }
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <>{children}</>
}
