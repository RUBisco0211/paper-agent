// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { AppRoutes } from "@/app/router"
import { ApiProvider } from "@/lib/api/provider"
import { AuthProvider } from "@/lib/auth/provider"

/** Minimal ResizeObserver for Radix primitives under jsdom. */
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

function renderApp(fetchImpl: typeof fetch, entries: string[] = ["/"]) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl }}>
        <AuthProvider>
          <MemoryRouter initialEntries={entries}>
            <AppRoutes />
          </MemoryRouter>
        </AuthProvider>
      </ApiProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverStub)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("app bootstrap", () => {
  it("falls back to the login page when the refresh cookie is invalid", async () => {
    const fetchImpl = vi.fn(async () =>
      json({ code: "refresh_token_invalid", message: "刷新令牌无效或已过期" }, 401),
    )

    renderApp(fetchImpl as unknown as typeof fetch, ["/"])

    expect(await screen.findByText("登录 Paper Agent")).toBeTruthy()
    // Bootstrap must not try to read the current user without a token.
    expect(
      (fetchImpl.mock.calls as unknown as [string][]).map(([url]) => url),
    ).toEqual(["http://api.test/v1/auth/refresh"])
  })

  it("restores the session and shows the shell with the paper library", async () => {
    const fetchImpl = vi.fn(async (input: string | URL) => {
      const url = String(input)
      if (url.endsWith("/v1/auth/refresh")) {
        return json({
          access_token: "token-1",
          token_type: "bearer",
          expires_in: 900,
          expires_at: new Date(Date.now() + 900_000).toISOString(),
        })
      }
      if (url.endsWith("/v1/auth/me")) {
        return json({
          id: "u1",
          email: "reader@example.com",
          display_name: "Reader",
          created_at: "2026-09-17T00:00:00Z",
        })
      }
      if (url.includes("/v1/papers")) {
        return json({ items: [], total: 0, limit: 20, offset: 0 })
      }
      return json({ items: [], total: 0, limit: 100, offset: 0 })
    })

    renderApp(fetchImpl as unknown as typeof fetch, ["/library"])

    expect(await screen.findByText("论文库还是空的")).toBeTruthy()
    expect(screen.getByRole("link", { name: /论文库/ })).toBeTruthy()
    expect(screen.getByText("reader@example.com")).toBeTruthy()
  })
})
