import { QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { RouterProvider } from "react-router-dom"

import { ApiProvider } from "@/lib/api/provider"
import { AuthProvider } from "@/lib/auth/provider"
import { Toaster } from "@/components/ui/sonner"
import { createAppRouter } from "@/app/router"
import { createQueryClient } from "@/app/query"
import { ThemeProvider } from "@/lib/theme/theme-provider"

import "./index.css"

const container = document.getElementById("root")

if (!container) {
  throw new Error("缺少 #root 挂载节点")
}

const queryClient = createQueryClient()
const router = createAppRouter()

createRoot(container).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <ApiProvider>
          <AuthProvider>
            <RouterProvider router={router} />
            <Toaster />
          </AuthProvider>
        </ApiProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
