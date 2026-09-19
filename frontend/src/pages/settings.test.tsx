// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { ApiProvider } from "@/lib/api/provider"
import { SettingsPage } from "@/pages/settings"

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

const CATALOG = {
  providers: [
    {
      id: "openai",
      label: "OpenAI",
      models: [{ id: "gpt-4.1-mini", label: "GPT-4.1 Mini", context_size: 1047576 }],
    },
    {
      id: "deepseek",
      label: "DeepSeek",
      models: [{ id: "deepseek-chat", label: "DeepSeek Chat", context_size: 128000 }],
    },
  ],
}

describe("SettingsPage", () => {
  beforeEach(() => {
    const values = new Map<string, string>()
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
      clear: () => values.clear(),
    })
  })

  it("uses catalog selections and only asks the user to type an API key", async () => {
    const fetchImpl = vi.fn(async () => json(CATALOG))
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

    expect(fetchImpl).toHaveBeenCalledWith(
      "http://api.test/v1/llm-catalog",
      expect.anything(),
    )
    const provider = await screen.findByRole("combobox", { name: "提供商" })
    expect(screen.getAllByRole("combobox")).toHaveLength(2)
    expect(screen.getByLabelText("API Key").getAttribute("type")).toBe("password")

    await user.click(provider)
    await user.click(screen.getByRole("option", { name: "DeepSeek" }))
    expect(screen.getByRole("combobox", { name: "模型" }).textContent).toContain(
      "DeepSeek Chat",
    )
    await user.type(screen.getByLabelText("API Key"), "test-key")
    await user.click(screen.getByRole("button", { name: "保存" }))

    expect(JSON.parse(localStorage.getItem("paper-agent.llm-config") ?? "{}")).toEqual({
      provider: "deepseek",
      model: "deepseek-chat",
      api_key: "test-key",
    })
  })
})
