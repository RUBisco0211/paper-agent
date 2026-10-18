import { QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { ApiProvider } from "@/components/providers/ApiProvider"
import { AuthProvider } from "@/components/providers/AuthProvider"
import { Toaster } from "@/components/ui/Sonner"
import { TooltipProvider } from "@/components/ui/Tooltip"
import App from "@/app/App"
import { createQueryClient } from "@/app/query"
import { ThemeProvider } from "@/components/providers/ThemeProvider"
import { clearLlmConfig } from "@/lib/settings/llmConfig"

import "./index.css"
import "@/i18n"

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
