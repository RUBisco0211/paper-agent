// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { ApiProvider } from "@/lib/api/provider"
import { SessionWorkspacePage } from "@/pages/session-workspace"

const SESSION = {
  id: "s1",
  title: "注意力机制",
  scope: "library",
  project_id: null,
  pending: { steering: 0, follow_up: 0 },
  pending_messages: [],
  is_generating: false,
  created_at: "2026-09-17T00:00:00Z",
  updated_at: "2026-09-17T00:00:00Z",
}

const ENTRY = {
  id: "e1",
  sequence: 1,
  parent_id: null,
  type: "message",
  timestamp: "2026-09-17T00:00:00Z",
  schema_version: 1,
  payload: { role: "user", content: "核心贡献是什么？" },
}

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

function renderWorkspace(fetchImpl: typeof fetch) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl }}>
        <MemoryRouter initialEntries={["/sessions/s1"]}>
          <Routes>
            <Route path="/sessions/:sessionId" element={<SessionWorkspacePage />} />
          </Routes>
        </MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>,
  )
}

describe("SessionWorkspacePage", () => {
  it("renders the history and the composer without runtime errors", async () => {
    const fetchImpl = vi.fn(async (input: string | URL) => {
      const url = String(input)
      if (url.includes("/events")) {
        return new Response(new ReadableStream({ start: (c) => c.close() }), {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        })
      }
      if (url.includes("/entries")) {
        return json({ items: [ENTRY], total: 1, limit: 200, offset: 0 })
      }
      return json(SESSION)
    })

    renderWorkspace(fetchImpl as unknown as typeof fetch)

    expect(await screen.findByText("注意力机制")).toBeTruthy()
    expect(await screen.findByText("核心贡献是什么？")).toBeTruthy()
    expect(screen.getByRole("textbox")).toBeTruthy()
    expect(screen.getByRole("button", { name: /发送/ })).toBeTruthy()
    // 空闲会话不展示投递方式选择
    expect(screen.queryByRole("radio", { name: /排队追问/ })).toBeNull()
  })

  it("keeps the same top bar height as other pages", async () => {
    const fetchImpl = vi.fn(async (input: string | URL) => {
      const url = String(input)
      if (url.includes("/events")) {
        return new Response(new ReadableStream({ start: (c) => c.close() }), {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        })
      }
      if (url.includes("/entries")) {
        return json({ items: [], total: 0, limit: 200, offset: 0 })
      }
      return json(SESSION)
    })

    renderWorkspace(fetchImpl as unknown as typeof fetch)

    const header = await screen.findByRole("banner")
    // 顶栏统一走 PageHeader（h-16 + border-b），项目页与工作区保持一致
    expect(header.className).toContain("h-16")
    expect(header.className).toContain("border-b")
  })

  it("shows the delivery mode and stop control while generating", async () => {
    const fetchImpl = vi.fn(async (input: string | URL) => {
      const url = String(input)
      if (url.includes("/events")) {
        return new Response(new ReadableStream({ start: (c) => c.close() }), {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        })
      }
      if (url.includes("/entries")) {
        return json({ items: [], total: 0, limit: 200, offset: 0 })
      }
      return json({ ...SESSION, is_generating: true })
    })

    renderWorkspace(fetchImpl as unknown as typeof fetch)

    expect(await screen.findByRole("radio", { name: /调整当前回答/ })).toBeTruthy()
    expect(screen.getByRole("radio", { name: /排队追问/ })).toBeTruthy()
    expect(screen.getByRole("button", { name: /停止/ })).toBeTruthy()
  })
})
