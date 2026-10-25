// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { PaperDetailSheet } from "@/components/papers/PaperDetailSheet"
import { ApiProvider } from "@/components/providers/ApiProvider"

vi.mock("@/components/papers/PdfViewer", () => ({ PdfViewer: () => <div>重复 PDF 预览</div> }))

const PAPER = {
  id: "p1",
  title: "注意力机制",
  authors: ["Vaswani"],
  year: 2017,
  venue: null,
  doi: null,
  arxiv_id: null,
  source: "upload",
  original_filename: "attention.pdf",
  added_at: "2026-09-17T00:00:00Z",
  capabilities: {
    has_source: false,
    has_metadata: true,
    has_parsed: true,
    has_index: true,
    has_embedding: false,
  },
  processing: { job_id: null, status: null, current_stage: null, error_code: null },
  abstract: null,
  metadata_status: "recognized",
  metadata: null,
  metadata_sources: null,
  pdf: { available: false, page_count: null, byte_size: null },
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

describe("PaperDetailSheet", () => {
  it("PaperDetailSheet omits the PDF viewer when paper information opens", async () => {
    const fetchImpl = vi.fn(async (input: string | URL) => String(input).includes("/v1/projects")
      ? json({ items: [], total: 0, limit: 100, offset: 0 })
      : json({ ...PAPER, capabilities: { ...PAPER.capabilities, has_source: true }, pdf: { available: true, page_count: 2, byte_size: 1000 } }))
    render(<QueryClientProvider client={createQueryClient()}>
      <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch }}>
        <MemoryRouter><PaperDetailSheet paperId="p1" onOpenChange={() => {}} /></MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>)
    expect(await screen.findByText("注意力机制")).toBeTruthy()
    expect(screen.queryByText("重复 PDF 预览")).toBeNull()
    expect(screen.queryByRole("heading", { name: "原文" })).toBeNull()
  })
  it("leaves progress to the import queue instead of duplicating it", async () => {
    const fetchImpl = vi.fn(async (input: string | URL) => {
      if (String(input).includes("/v1/projects"))
        return json({ items: [], total: 0, limit: 100, offset: 0 })
      return json({ ...PAPER, import_status: "ready" })
    })
    render(
      <QueryClientProvider client={createQueryClient()}>
        <ApiProvider
          options={{ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch }}
        >
          <MemoryRouter>
            <PaperDetailSheet paperId="p1" onOpenChange={() => {}} />
          </MemoryRouter>
        </ApiProvider>
      </QueryClientProvider>,
    )
    await screen.findAllByText("书目信息")
    expect(screen.queryByRole("region", { name: "处理进度" })).toBeNull()
    expect(screen.queryByRole("list", { name: "处理进度" })).toBeNull()
  })

  it("starts a single-paper session from a paper", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = vi.fn(async (input: string | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push({ url, init })
      if (url.includes("/v1/projects")) {
        return json({ items: [], total: 0, limit: 100, offset: 0 })
      }
      if (url.endsWith("/v1/sessions")) {
        return json(
          {
            id: "s1",
            title: "注意力机制",
            scope: "library",
            project_id: null,
            pending: { steering: 0, follow_up: 0 },
            created_at: "2026-09-17T00:00:00Z",
            updated_at: "2026-09-17T00:00:00Z",
          },
          201,
        )
      }
      return json(PAPER)
    })

    const user = userEvent.setup()
    render(
      <QueryClientProvider client={createQueryClient()}>
        <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: fetchImpl as unknown as typeof fetch }}>
          <MemoryRouter initialEntries={["/library"]}>
            <Routes>
              <Route
                path="/library"
                element={<PaperDetailSheet paperId="p1" onOpenChange={() => {}} />}
              />
              <Route path="/sessions/:sessionId" element={<p>工作区</p>} />
            </Routes>
          </MemoryRouter>
        </ApiProvider>
      </QueryClientProvider>,
    )

    await user.click(await screen.findByRole("button", { name: /提问/ }))

    const created = calls.find((call) => call.url.endsWith("/v1/sessions"))
    expect(created).toBeTruthy()
    const body = JSON.parse(String(created?.init?.body))
    // 单篇文献会话：带上条目 ID，且不属于任何项目
    expect(body.paper_id).toBe("p1")
    expect(body).not.toHaveProperty("project_id")
    expect(body.title).toBe("注意力机制")
  })
})
