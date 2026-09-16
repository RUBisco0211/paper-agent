import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import "./index.css"

const container = document.getElementById("root")

if (!container) {
  throw new Error("缺少 #root 挂载节点")
}

createRoot(container).render(
  <StrictMode>
    <main className="flex min-h-screen items-center justify-center p-8">
      <div className="text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Paper Agent</h1>
        <p className="text-muted-foreground mt-2 text-sm">
          前端脚手架与 API 调用层已就绪，页面尚未实现。
        </p>
      </div>
    </main>
  </StrictMode>,
)
