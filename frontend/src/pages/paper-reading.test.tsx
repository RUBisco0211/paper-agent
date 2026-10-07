// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { ApiProvider } from "@/lib/api/provider"
import { PaperReadingPage } from "@/pages/paper-reading"

vi.mock("@/components/papers/pdf-viewer", () => ({
  PdfViewer: ({ target }: { target?: { page: number } }) => <p>PDF 第 {target?.page ?? 1} 页</p>,
}))

it("shows MinerU block type tabs and locates the selected block when it is clicked", async () => {
  const fetchImpl = vi.fn(async (input: string | URL) => {
    const url = String(input)
    if (url.endsWith("/blocks/2")) {
      return new Response(JSON.stringify({ id: 2, type: "table", page: 3, text: "结果表", bbox: [10, 20, 100, 80], page_size: [612, 792], coordinate_system: "page" }), { headers: { "Content-Type": "application/json" } })
    }
    if (url.includes("/blocks")) {
      return new Response(JSON.stringify({
        types: ["text", "table"],
        items: url.includes("type=table")
          ? [{ id: 2, type: "table", page: 3, text: "结果表", bbox: [10, 20, 100, 80], page_size: [612, 792] }]
          : [{ id: 1, type: "text", page: 1, text: "正文", bbox: null, page_size: null }],
        total: 1, offset: 0, limit: 50,
      }), { headers: { "Content-Type": "application/json" } })
    }
    return new Response(JSON.stringify({ id: "p1", title: "测试文献", authors: [], pdf: { available: true }, capabilities: { has_fulltext: true } }), { headers: { "Content-Type": "application/json" } })
  })
  render(
    <QueryClientProvider client={createQueryClient()}>
      <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch }}>
        <MemoryRouter initialEntries={["/library/p1"]}>
          <Routes><Route path="/library/:paperId" element={<PaperReadingPage />} /></Routes>
        </MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>,
  )
  const user = userEvent.setup()
  await user.click(await screen.findByRole("tab", { name: "表格" }))
  await user.click(await screen.findByRole("button", { name: /结果表/ }))
  expect(screen.getByText("PDF 第 3 页")).toBeTruthy()
})

it("previews images and equations and offers copy actions without a redundant heading", async () => {
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:preview"), revokeObjectURL: vi.fn() }))
  const fetchImpl = vi.fn(async (input: string | URL) => {
    const url = String(input)
    if (url.endsWith("/blocks/2/image")) return new Response(new Blob(["image"], { type: "image/png" }))
    if (url.includes("/blocks")) {
      const type = new URL(url).searchParams.get("type") ?? "text"
      const items = {
        text: [{ id: 0, type: "text", page: 1, text: "可复制正文" }],
        footnote: [{ id: 1, type: "footnote", page: 1, text: "脚注" }],
        image: [{ id: 2, type: "image", page: 2, text: "图注", has_image: true }],
        equation: [{ id: 3, type: "equation", page: 3, text: "E = mc^2", formula: "E = mc^2" }],
      }[type] ?? []
      return new Response(JSON.stringify({ types: ["text", "footnote", "image", "equation"], items, total: 1, offset: 0, limit: 50 }), { headers: { "Content-Type": "application/json" } })
    }
    return new Response(JSON.stringify({ id: "p1", title: "测试文献", authors: [], pdf: { available: true }, capabilities: { has_fulltext: true } }), { headers: { "Content-Type": "application/json" } })
  })
  render(<QueryClientProvider client={createQueryClient()}>
    <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch }}>
      <MemoryRouter initialEntries={["/library/p1"]}>
        <Routes><Route path="/library/:paperId" element={<PaperReadingPage />} /></Routes>
      </MemoryRouter>
    </ApiProvider>
  </QueryClientProvider>)
  const user = userEvent.setup()
  expect(screen.queryByText("原文片段")).toBeNull()
  expect(await screen.findByRole("tab", { name: "footnote" })).toBeTruthy()
  await user.click(await screen.findByRole("button", { name: "复制正文" }))
  expect(await navigator.clipboard.readText()).toBe("可复制正文")
  await user.click(screen.getByRole("tab", { name: "图片" }))
  expect(await screen.findByRole("img", { name: "图注" })).toBeTruthy()
  await user.click(screen.getByRole("tab", { name: "公式" }))
  await user.click(await screen.findByRole("button", { name: "复制公式" }))
  expect(await navigator.clipboard.readText()).toBe("E = mc^2")
  expect(document.querySelector(".katex")).toBeTruthy()
})
