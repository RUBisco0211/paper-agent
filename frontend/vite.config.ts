import path from "node:path"

import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import svgr from "vite-plugin-svgr"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss(), svgr()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
      "@upstream": path.resolve(import.meta.dirname, "./src/upstream"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 前端默认通过同源代理访问后端，避免开发期跨站 Cookie 问题。
      "/v1": {
        target: process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test/setup.ts"],
  },
})
