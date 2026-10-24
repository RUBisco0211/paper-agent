// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { RetrievalSection } from "@/components/settings/RetrievalSection"

const api = {
  serviceCredentials: {
    list: vi.fn(),
    save: vi.fn(),
    remove: vi.fn(),
  },
}

vi.mock("@/components/providers/ApiProvider", () => ({ useApi: () => ({ api }) }))

function renderWith(savedKey: string | null) {
  api.serviceCredentials.list.mockResolvedValue({
    items: savedKey
      ? [{ kind: "embedding", label: "Embedding", fields: { api_key: "<set>" } }]
      : [],
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <RetrievalSection />
    </QueryClientProvider>,
  )
}

describe("RetrievalSection", () => {
  it("names the provider and offers key setup without describing storage internals", async () => {
    renderWith(null)
    expect(await screen.findByLabelText("SiliconFlow API Key")).toBeTruthy()
    expect(screen.getByRole("link", { name: "获取 SiliconFlow API Key" }).getAttribute("href"))
      .toBe("https://cloud.siliconflow.cn/account/ak")
    expect(screen.queryByText(/转成向量|文献片段比对|密钥保存在/)).toBeNull()
  })
  it("explains that ingestion vectors are paid by the site and searches by the user", async () => {
    renderWith(null)

    expect(await screen.findByText(/文献入库由本站承担费用/)).toBeTruthy()
    expect(await screen.findByText("尚未配置")).toBeTruthy()
  })

  it("saves the key under the embedding credential kind", async () => {
    renderWith(null)
    api.serviceCredentials.save.mockResolvedValue({ kind: "embedding", label: "", fields: {} })

    fireEvent.change(await screen.findByLabelText("SiliconFlow API Key"), {
      target: { value: "sk-user" },
    })
    fireEvent.click(screen.getByRole("button", { name: "保存密钥" }))

    await waitFor(() =>
      expect(api.serviceCredentials.save).toHaveBeenCalledWith("embedding", {
        label: "Embedding",
        fields: { api_key: "sk-user" },
      }),
    )
  })

  it("offers removal only after a key is saved", async () => {
    renderWith("sk-saved")

    expect(await screen.findByRole("button", { name: "移除" })).toBeTruthy()
    expect(screen.getByText("密钥已隐藏")).toBeTruthy()
  })
})
