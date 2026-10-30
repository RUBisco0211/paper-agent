// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { PaperMarkdownView, splitMarkdownPages } from "@/components/papers/PaperMarkdownView"
import { ApiProvider } from "@/components/providers/ApiProvider"

const visiblePages = { indices: [0], all: 1 }

// 只让第一页进入文档，用来确认组件按可视窗口挂载分页。
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }: { count: number }) => {
    visiblePages.all = count
    return {
      getVirtualItems: () => visiblePages.indices.map((index) => ({ index, key: index, start: index * 100 })),
      getTotalSize: () => count * 100,
      measureElement: () => {},
    }
  },
}))

function renderView(markdown: string, onQuote = vi.fn(() => true)) {
  const fetchImpl = vi.fn(async (input: string | URL) => {
    const url = String(input)
    if (url.endsWith("/markdown")) {
      return new Response(JSON.stringify({ markdown }), { headers: { "Content-Type": "application/json" } })
    }
    return new Response(JSON.stringify({ id: "p1" }), { headers: { "Content-Type": "application/json" } })
  })
  render(<QueryClientProvider client={createQueryClient()}>
    <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch }}>
      <PaperMarkdownView
        paperId="p1"
        title="测试文献"
        version="v1"
        onBackToPdf={() => {}}
        onQuote={onQuote}
      />
    </ApiProvider>
  </QueryClientProvider>)
  return { onQuote }
}

it("splits the full text into page sized chunks without cutting a code fence or table", () => {
  const fence = "```\n" + "const x = 1\n".repeat(200) + "```"
  const table = "| a | b |\n| - | - |\n" + "| 1 | 2 |\n".repeat(200)
  const markdown = `# 标题\n\n${"正文段落。\n\n".repeat(200)}${fence}\n\n${table}\n\n## 小结\n\n结尾`

  const pages = splitMarkdownPages(markdown, 400)

  expect(pages.length).toBeGreaterThan(1)
  const fenced = pages.find((page) => page.includes("const x = 1"))
  expect((fenced?.match(/```/g) ?? []).length).toBe(2)
  const tablePage = pages.find((page) => page.includes("| 1 | 2 |"))
  expect(tablePage?.includes("| a | b |")).toBe(true)
})

it("renders only the markdown pages inside the visible window", async () => {
  visiblePages.indices = [0]
  renderView(`第一页内容\n\n${"填充段落。\n\n".repeat(900)}第二页内容`)

  expect(await screen.findByText(/第一页内容/)).toBeTruthy()
  expect(visiblePages.all).toBeGreaterThan(1)
  expect(screen.queryByText(/第二页内容/)).toBeNull()
})

it("adds a markdown selection to the conversation as full text evidence", async () => {
  visiblePages.indices = [0]
  const { onQuote } = renderView("INTRO TEXT selected by the reader.", vi.fn(() => true))

  const paragraph = await screen.findByText(/INTRO TEXT/)
  const range = document.createRange()
  range.selectNodeContents(paragraph)
  const selection = window.getSelection()
  selection?.removeAllRanges()
  selection?.addRange(range)
  paragraph.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }))

  const user = userEvent.setup()
  await user.click(await screen.findByRole("button", { name: "添加到对话" }))

  expect(onQuote).toHaveBeenCalledWith(expect.objectContaining({
    kind: "markdown_selection",
    user_paper_id: "p1",
    version: "v1",
    selected_text: "INTRO TEXT selected by the reader.",
    source_title: "测试文献",
  }))
})
