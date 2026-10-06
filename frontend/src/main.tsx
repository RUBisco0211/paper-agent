import { QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { ApiProvider } from "@/lib/api/provider"
import { AuthProvider } from "@/lib/auth/provider"
import { Toaster } from "@upstream/components/ui/sonner"
import { TooltipProvider } from "@upstream/components/ui/tooltip"
import App from "@upstream/App"
import { createQueryClient } from "@/app/query"
import { ThemeProvider } from "@/lib/theme/theme-provider"
import { clearLlmConfig } from "@/lib/settings/llm-config"

import "./upstream/index.css"
import "./upstream/i18n"

const container = document.getElementById("root")

if (!container) {
  throw new Error("缺少 #root 挂载节点")
}

const queryClient = createQueryClient()
clearLlmConfig()

createRoot(container).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <ApiProvider>
          <AuthProvider>
            <TooltipProvider>
              <App />
              <Toaster />
            </TooltipProvider>
          </AuthProvider>
        </ApiProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
