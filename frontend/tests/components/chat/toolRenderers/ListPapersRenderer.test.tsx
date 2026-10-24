// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { ListPapersRenderer } from "@/components/chat/toolRenderers/ListPapersRenderer"
import type { ToolCallWithResult } from "@/components/chat/toolRenderers/types"

const openers = vi.hoisted(() => ({
  // Calling happens through the hoisted fn so a per-test detach option works.
  handle: vi.fn(),
  available: true,
}))

vi.mock("@/components/chat/CitationProvider", () => ({
  useCitationOpen: () => null,
  usePaperOpen: () =>
    openers.available ? (reference: unknown) => openers.handle(reference) : null,
}))

function pair(papers: unknown[]): ToolCallWithResult {
  return {
    call: { type: "tool_call", id: "call-1", name: "list_papers", input: "{}" },
    result: {
      type: "tool_result",
      id: "result-1",
      name: "list_papers",
      output: JSON.stringify({ total: papers.length, papers }),
    },
  } as ToolCallWithResult
}

function renderBody(papers: unknown[]) {
  const node = ListPapersRenderer.renderBody?.(pair(papers), ((key: string) => key) as never)
  render(<QueryClientProvider client={createQueryClient()}>{node}</QueryClientProvider>)
}

// Shape copied from the internal list endpoint: compact, paper_id-keyed.
const ready = {
  paper_id: "entry-1",
  title: "Attention Is All You Need",
  authors: ["Ashish Vaswani"],
  year: 2017,
  venue: "NeurIPS",
  has_fulltext: true,
}

describe("list_papers tool", () => {
  beforeEach(() => {
    openers.available = true
    openers.handle.mockReset()
  })

  it("lists papers with title, authors and state without exposing internal ids", () => {
    renderBody([ready])
    const button = screen.getByRole("button", { name: /Attention Is All You Need/ })
    expect(button.textContent).toContain("Ashish Vaswani")
    expect(button.textContent).toContain("可检索")
    expect(button.textContent).not.toContain("entry-1")
  })

  it("opens the paper in the conversation sidebar when an entry is clicked", () => {
    let opened: unknown = null
    openers.available = true
    openers.handle.mockImplementation((reference: unknown) => { opened = reference })
    renderBody([ready])

    fireEvent.click(screen.getByRole("button", { name: /Attention Is All You Need/ }))

    expect(opened).toEqual({
      kind: "paper",
      user_paper_id: "entry-1",
      page: null,
    })
  })

  it("reports the parsing state and keeps the entry clickable when full text is missing", () => {
    let opened: unknown = null
    openers.available = true
    openers.handle.mockImplementation((reference: unknown) => { opened = reference })
    renderBody([{ ...ready, has_fulltext: false }])

    const button = screen.getByRole("button", { name: /Attention Is All You Need/ })
    expect(button.textContent).toContain("待补全文")
    fireEvent.click(button)
    expect(opened).toEqual({ kind: "paper", user_paper_id: "entry-1", page: null })
  })

  it("keeps the card non-clickable when no conversation sidebar can open it", () => {
    openers.available = false
    renderBody([ready])

    const card = screen.getByText("Attention Is All You Need").closest("button")
    expect(card).toBeNull()
    expect(screen.queryByRole("button", { name: /Attention Is All You Need/ })).toBeNull()
  })

  it("says the library is empty instead of rendering an empty list", () => {
    renderBody([])
    expect(screen.getByText("暂无文献")).toBeTruthy()
  })
})
