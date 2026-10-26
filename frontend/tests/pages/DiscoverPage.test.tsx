// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen, within, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { DiscoverPage } from "@/pages/DiscoverPage"

const api = {
  retrieval: { discover: vi.fn(async () => ({ papers: [
    { source_id: "https://doi.org/10.1234/one", title: "First paper", doi: "10.1234/one", pdf_url: "https://example.org/one.pdf", sources: ["crossref"] },
    { source_id: "https://example.org/two", title: "Second paper", doi: null, pdf_url: null, sources: ["openalex"] },
  ], failed_sources: [] })) },
  imports: { start: vi.fn(async () => ({ id: "i1", status: "pending" })) },
}
vi.mock("@/components/providers/ApiProvider", () => ({ useApi: () => ({ api }) }))
vi.mock("@/components/providers/ImportQueueProvider", () => ({ useImportQueue: () => ({ setOpen: vi.fn() }) }))

it("searches externally and queues only an identified paper", async () => {
  const user = userEvent.setup()
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter><DiscoverPage /></MemoryRouter></QueryClientProvider>)
  await user.type(screen.getByRole("searchbox", { name: "搜索文献" }), "agent safety")
  await user.click(screen.getByRole("button", { name: "搜索" }))
  expect(await screen.findByText("First paper")).toBeTruthy()
  expect(screen.getByRole("link", { name: "PDF" }).getAttribute("href")).toBe("https://example.org/one.pdf")
  expect(screen.getByRole("checkbox", { name: /Second paper/ }).hasAttribute("disabled")).toBe(true)
  await user.click(screen.getByRole("checkbox", { name: /First paper/ }))
  await user.click(screen.getByRole("button", { name: /选择入库/ }))
  const dialog = screen.getByRole("dialog", { name: "导入所选文献" })
  await user.click(within(dialog).getByRole("button", { name: "确认导入" }))
  // A request only records the identifier; the queue shows it from there.
  await waitFor(() => expect(api.imports.start).toHaveBeenCalledWith("10.1234/one"))
})
