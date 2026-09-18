// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { ApiProvider } from "@/lib/api/provider"
import { SettingsPage } from "@/pages/settings"

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

describe("SettingsPage", () => {
  it("offers the providers allowed by the deployment", async () => {
    const fetchImpl = vi.fn(async () =>
      json({ providers: ["dashscope", "deepseek", "openai"] }),
    )
    const user = userEvent.setup()

    render(
      <QueryClientProvider client={createQueryClient()}>
        <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl }}>
          <MemoryRouter>
            <SettingsPage />
          </MemoryRouter>
        </ApiProvider>
      </QueryClientProvider>,
    )

    // 名单来自后端，不在前端硬编码
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://api.test/v1/llm-providers",
      expect.anything(),
    )
    await user.click(screen.getByRole("combobox", { name: /Provider/ }))
    expect(await screen.findByRole("option", { name: "dashscope" })).toBeTruthy()
    expect(screen.getByRole("option", { name: "deepseek" })).toBeTruthy()
    expect(screen.getByRole("option", { name: "openai" })).toBeTruthy()
  })
})
