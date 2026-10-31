// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { ApiProvider } from "@/components/providers/ApiProvider"
import { AuthProvider, useAuth } from "@/components/providers/AuthProvider"

const USER = {
  id: "u1",
  email: "reader@example.com",
  display_name: "读者",
  created_at: "2026-10-01T00:00:00Z",
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

function Probe() {
  const { status, preferences } = useAuth()
  return <p>{`${status}|${preferences?.timezone ?? "-"}|${preferences?.notify_email_default ?? "-"}`}</p>
}

function renderAuth(preferences: { timezone: string | null; notify_email_default: boolean }) {
  const calls: string[] = []
  const fetchImpl = vi.fn(async (input: string | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? "GET"
    calls.push(`${method} ${new URL(url).pathname}`)
    if (url.endsWith("/v1/auth/refresh")) {
      return json({ access_token: "token", expires_in: 900, expires_at: "", user: USER })
    }
    if (url.endsWith("/v1/auth/me")) return json(USER)
    if (url.endsWith("/v1/auth/preferences")) {
      return method === "PATCH" ? json({ ...preferences, notify_email_default: true }) : json(preferences)
    }
    if (url.endsWith("/v1/auth/timezone")) {
      return json({ timezone: JSON.parse(String(init?.body)).timezone })
    }
    return json({})
  })
  render(<QueryClientProvider client={createQueryClient()}>
    <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch }}>
      <AuthProvider><Probe /></AuthProvider>
    </ApiProvider>
  </QueryClientProvider>)
  return calls
}

it("fills the timezone from the browser once when the account has none", async () => {
  const calls = renderAuth({ timezone: null, notify_email_default: false })

  const state = await screen.findByText(/^authenticated\|/)
  expect(state.textContent).toMatch(/^authenticated\|[A-Za-z]+\/[A-Za-z_]+\|false$/)
  expect(calls.filter((call) => call === "PATCH /v1/auth/timezone")).toHaveLength(1)
})

it("keeps the timezone the account already saved", async () => {
  const calls = renderAuth({ timezone: "Europe/Berlin", notify_email_default: false })

  expect((await screen.findByText(/^authenticated\|/)).textContent)
    .toBe("authenticated|Europe/Berlin|false")
  expect(calls.filter((call) => call === "PATCH /v1/auth/timezone")).toHaveLength(0)
})
