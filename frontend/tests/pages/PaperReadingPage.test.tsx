// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import type { ReactNode } from "react"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { ApiProvider } from "@/components/providers/ApiProvider"
import { PaperReadingPage } from "@/pages/PaperReadingPage"

vi.mock("@/components/papers/PdfViewer", () => ({
  PdfViewer: ({ target, onClearTarget }: { target?: { page: number }; onClearTarget?: () => void }) => <div><p>PDF 第 {target?.page ?? 1} 页</p><button type="button" onClick={onClearTarget}>文献空白处</button></div>,
}))
// jsdom 没有布局，虚拟列表量不到可视高度；这里让每个分页都落到文档里。
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }: { count: number }) => ({
    getVirtualItems: () => Array.from({ length: count }, (_, index) => ({ index, key: index, start: index * 100 })),
    getTotalSize: () => count * 100,
    measureElement: () => {},
  }),
}))
vi.mock("@/components/ui/Resizable", () => ({
  ResizablePanelGroup: ({ children, className }: { children: ReactNode; className?: string }) => <div className={className}>{children}</div>,
  ResizablePanel: ({ children, className, defaultSize }: { children: ReactNode; className?: string; defaultSize?: string }) => <div className={className} data-default-size={defaultSize}>{children}</div>,
  ResizableHandle: ({ "aria-label": label }: { "aria-label": string }) => <div role="separator" aria-label={label} />,
}))

it("shows MinerU block type tabs and locates a block only when its locate button is clicked", async () => {
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
    return new Response(JSON.stringify({ id: "p1", title: "测试文献", authors: [], pdf: { available: true }, capabilities: { has_parsed: true } }), { headers: { "Content-Type": "application/json" } })
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
  await user.click(await screen.findByText("结果表"))
  expect(screen.getByText("PDF 第 1 页")).toBeTruthy()
  await user.click(screen.getByRole("button", { name: "定位分块" }))
  expect(screen.getByText("PDF 第 3 页")).toBeTruthy()
  await user.click(screen.getByRole("button", { name: "文献空白处" }))
  expect(screen.getByText("PDF 第 1 页")).toBeTruthy()
})

it("adds a paper quote without requiring a comment and permits retry after rejection", async () => {
  const onQuote = vi.fn().mockReturnValueOnce(false).mockReturnValueOnce(true)
  const fetchImpl = vi.fn(async (input: string | URL) => {
    const url = String(input)
    if (url.includes("/blocks")) return new Response(JSON.stringify({ types: ["text"], items: [{ id: 4, type: "text", page: 2, text: "需要核对的段落" }], total: 1, offset: 0, limit: 50 }), { headers: { "Content-Type": "application/json" } })
    return new Response(JSON.stringify({ id: "p1", title: "测试文献", authors: [], pdf: { available: false }, artifact_version: "v1", capabilities: { has_parsed: true } }), { headers: { "Content-Type": "application/json" } })
  })
  render(<QueryClientProvider client={createQueryClient()}><ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch }}>
    <MemoryRouter><PaperReadingPage paperId="p1" embedded onQuote={onQuote} onBack={vi.fn()} /></MemoryRouter>
  </ApiProvider></QueryClientProvider>)
  const user = userEvent.setup()
  await user.click(await screen.findByRole("button", { name: "添加到对话" }))
  expect(onQuote).toHaveBeenCalledWith(expect.objectContaining({ kind: "parsed_block", block_id: 4, selected_text: "需要核对的段落", comment: "" }))
  expect(screen.queryByRole("textbox", { name: "引用评论" })).toBeNull()
  await user.click(screen.getByRole("button", { name: "添加到对话" }))
  expect(onQuote).toHaveBeenCalledTimes(2)
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
    return new Response(JSON.stringify({ id: "p1", title: "测试文献", authors: [], pdf: { available: true }, capabilities: { has_parsed: true } }), { headers: { "Content-Type": "application/json" } })
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

it("renders a MinerU display equation without showing its image fallback or raw delimiters", async () => {
  const fetchImpl = vi.fn(async (input: string | URL) => {
    const url = String(input)
    if (url.endsWith("/blocks/4/image")) return new Response(null, { status: 404 })
    if (url.includes("/blocks")) return new Response(JSON.stringify({
      types: ["equation"], items: [{ id: 4, type: "equation", page: 4,
        text: "$$ E = mc^2 $$", formula: "$$ E = mc^2 $$", has_image: true }],
      total: 1, offset: 0, limit: 50,
    }), { headers: { "Content-Type": "application/json" } })
    return new Response(JSON.stringify({ id: "p1", title: "测试文献", authors: [], pdf: { available: true }, capabilities: { has_parsed: true } }), { headers: { "Content-Type": "application/json" } })
  })
  render(<QueryClientProvider client={createQueryClient()}>
    <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch }}>
      <MemoryRouter initialEntries={["/library/p1"]}>
        <Routes><Route path="/library/:paperId" element={<PaperReadingPage />} /></Routes>
      </MemoryRouter>
    </ApiProvider>
  </QueryClientProvider>)
  await screen.findByRole("tab", { name: "公式" })
  await waitFor(() => expect(document.querySelector(".katex")).toBeTruthy())
  expect(screen.queryByText("图片预览不可用")).toBeNull()
  expect(screen.queryByText(/\$\$ E = mc\^2 \$\$/)).toBeNull()
})

it("keeps the paper toolbars aligned and lets the block sidebar be resized", async () => {
  const fetchImpl = vi.fn(async (input: string | URL) => {
    const url = String(input)
    if (url.includes("/blocks")) return new Response(JSON.stringify({ types: ["text"], items: [], total: 0, offset: 0, limit: 50 }), { headers: { "Content-Type": "application/json" } })
    return new Response(JSON.stringify({ id: "p1", title: "测试文献", authors: [], pdf: { available: true }, capabilities: { has_parsed: true } }), { headers: { "Content-Type": "application/json" } })
  })
  render(<QueryClientProvider client={createQueryClient()}>
    <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch }}>
      <MemoryRouter initialEntries={["/library/p1"]}>
        <Routes><Route path="/library/:paperId" element={<PaperReadingPage />} /></Routes>
      </MemoryRouter>
    </ApiProvider>
  </QueryClientProvider>)
  expect(await screen.findByRole("tab", { name: "正文" })).toBeTruthy()
  expect(screen.getByRole("button", { name: "文献信息" }).querySelector("svg")).toBeTruthy()
  expect(screen.getByRole("separator", { name: "调整分块宽度" })).toBeTruthy()
  expect(screen.getByRole("complementary", { name: "文献分块" }).querySelector("[data-slot=tabs]")?.className).toContain("h-full")
})

it("PaperReadingPage starts PDF loading when metadata is pending", async () => {
  let resolveDetail: ((response: Response) => void) | undefined
  const fetchImpl = vi.fn((input: string | URL) => {
    if (String(input).endsWith("/v1/papers/p1")) return new Promise<Response>((resolve) => { resolveDetail = resolve })
    return Promise.resolve(new Response(JSON.stringify({ types: [], items: [], total: 0, offset: 0, limit: 50 }), { headers: { "Content-Type": "application/json" } }))
  })
  render(<QueryClientProvider client={createQueryClient()}>
    <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch }}>
      <MemoryRouter initialEntries={["/library/p1"]}>
        <Routes><Route path="/library/:paperId" element={<PaperReadingPage />} /></Routes>
      </MemoryRouter>
    </ApiProvider>
  </QueryClientProvider>)
  expect(screen.getByText("PDF 第 1 页")).toBeTruthy()
  resolveDetail?.(new Response(JSON.stringify({ id: "p1", title: "测试文献", authors: [], pdf: { available: true }, capabilities: { has_parsed: false } }), { headers: { "Content-Type": "application/json" } }))
})

it("PaperReadingPage opens a zoomable preview when a chart has an image", async () => {
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:chart"), revokeObjectURL: vi.fn() }))
  const fetchImpl = vi.fn(async (input: string | URL) => {
    const url = String(input)
    if (url.endsWith("/blocks/5/image")) return new Response(new Blob(["chart"], { type: "image/png" }))
    if (url.includes("/blocks")) return new Response(JSON.stringify({
      types: ["chart"], items: [{ id: 5, type: "chart", page: 2, text: "统计图", has_image: true }], total: 1, offset: 0, limit: 50,
    }), { headers: { "Content-Type": "application/json" } })
    return new Response(JSON.stringify({ id: "p1", title: "测试文献", authors: [], pdf: { available: true }, capabilities: { has_parsed: true } }), { headers: { "Content-Type": "application/json" } })
  })
  render(<QueryClientProvider client={createQueryClient()}>
    <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch }}>
      <MemoryRouter initialEntries={["/library/p1"]}>
        <Routes><Route path="/library/:paperId" element={<PaperReadingPage />} /></Routes>
      </MemoryRouter>
    </ApiProvider>
  </QueryClientProvider>)
  const user = userEvent.setup()
  await user.click(await screen.findByRole("button", { name: "查看图表" }))
  expect(await screen.findByRole("dialog", { name: "图表预览" })).toBeTruthy()
  await user.click(screen.getByRole("button", { name: "放大图片" }))
  expect(screen.getByText("125%")).toBeTruthy()
})

it("shows the markdown full text instead of the pdf and the block panel when the reader toggles the view", async () => {
  const fetchImpl = vi.fn(async (input: string | URL) => {
    const url = String(input)
    if (url.endsWith("/markdown")) {
      return new Response(JSON.stringify({ markdown: "## 摘要\n\n这是一段全文。" }), { headers: { "Content-Type": "application/json" } })
    }
    if (url.includes("/blocks")) {
      return new Response(JSON.stringify({ types: ["text"], items: [], total: 0, offset: 0, limit: 50 }), { headers: { "Content-Type": "application/json" } })
    }
    return new Response(JSON.stringify({ id: "p1", title: "测试文献", authors: [], pdf: { available: true }, capabilities: { has_parsed: true } }), { headers: { "Content-Type": "application/json" } })
  })
  render(<QueryClientProvider client={createQueryClient()}>
    <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch }}>
      <MemoryRouter initialEntries={["/library/p1"]}>
        <Routes><Route path="/library/:paperId" element={<PaperReadingPage />} /></Routes>
      </MemoryRouter>
    </ApiProvider>
  </QueryClientProvider>)
  const user = userEvent.setup()
  expect(await screen.findByRole("complementary", { name: "文献分块" })).toBeTruthy()
  await user.click(await screen.findByRole("button", { name: "切换到 Markdown 全文" }))
  expect(await screen.findByRole("heading", { name: "摘要" })).toBeTruthy()
  expect(screen.getByText("这是一段全文。")).toBeTruthy()
  expect(screen.queryByRole("complementary", { name: "文献分块" })).toBeNull()
  expect(screen.queryByText("PDF 第 1 页")).toBeNull()
  await user.click(screen.getByRole("button", { name: "切换到 PDF 原文" }))
  expect(screen.getByText("PDF 第 1 页")).toBeTruthy()
})

it("renders a markdown image from the paper asset endpoint", async () => {
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:markdown-figure"), revokeObjectURL: vi.fn() }))
  const fetchImpl = vi.fn(async (input: string | URL) => {
    const url = String(input)
    if (url.endsWith("/assets/images/figure-1.png")) return new Response(new Blob(["png"], { type: "image/png" }))
    if (url.endsWith("/markdown")) {
      return new Response(JSON.stringify({ markdown: "![图注](images/figure-1.png)" }), { headers: { "Content-Type": "application/json" } })
    }
    if (url.includes("/blocks")) {
      return new Response(JSON.stringify({ types: ["text"], items: [], total: 0, offset: 0, limit: 50 }), { headers: { "Content-Type": "application/json" } })
    }
    return new Response(JSON.stringify({ id: "p1", title: "测试文献", authors: [], pdf: { available: true }, capabilities: { has_parsed: true } }), { headers: { "Content-Type": "application/json" } })
  })
  render(<QueryClientProvider client={createQueryClient()}>
    <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch }}>
      <MemoryRouter initialEntries={["/library/p1"]}>
        <Routes><Route path="/library/:paperId" element={<PaperReadingPage />} /></Routes>
      </MemoryRouter>
    </ApiProvider>
  </QueryClientProvider>)
  const user = userEvent.setup()
  await user.click(await screen.findByRole("button", { name: "切换到 Markdown 全文" }))
  expect(await screen.findByRole("img", { name: "图注" })).toBeTruthy()
  expect(fetchImpl.mock.calls.some(([input]) => String(input).endsWith("/assets/images/figure-1.png"))).toBe(true)
})

it("disables the markdown view when the paper has no parsed full text", async () => {
  const fetchImpl = vi.fn(async (input: string | URL) => {
    const url = String(input)
    if (url.includes("/blocks")) return new Response(JSON.stringify({ types: [], items: [], total: 0, offset: 0, limit: 50 }), { headers: { "Content-Type": "application/json" } })
    return new Response(JSON.stringify({ id: "p1", title: "测试文献", authors: [], pdf: { available: true }, capabilities: { has_parsed: false } }), { headers: { "Content-Type": "application/json" } })
  })
  render(<QueryClientProvider client={createQueryClient()}>
    <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch }}>
      <MemoryRouter initialEntries={["/library/p1"]}>
        <Routes><Route path="/library/:paperId" element={<PaperReadingPage />} /></Routes>
      </MemoryRouter>
    </ApiProvider>
  </QueryClientProvider>)
  const toggle = await screen.findByRole("button", { name: "切换到 Markdown 全文" })
  expect((toggle as HTMLButtonElement).disabled).toBe(true)
})
