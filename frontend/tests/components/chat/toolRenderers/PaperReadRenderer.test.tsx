// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { CitationProvider } from "@/components/chat/CitationProvider"

import {
  PaperImageRenderer,
  PaperPageRenderer,
} from "@/components/chat/toolRenderers/PaperReadRenderer"
import type { ToolCallWithResult } from "@/components/chat/toolRenderers/types"

const PNG = "iVBORw0KGgoAAAANSUhEUg=="

function imagePair(
  meta: Record<string, unknown>,
  image?: { data: string; media_type: string },
): ToolCallWithResult {
  const output: unknown[] = [{ type: "text", text: JSON.stringify(meta) }]
  if (image) {
    output.push({
      type: "data",
      id: "data-1",
      created_at: "2026-10-29T00:00:00Z",
      source: { type: "base64", data: image.data, media_type: image.media_type },
    })
  }
  return {
    call: {
      type: "tool_call",
      id: "call-1",
      name: "read_paper_image",
      input: JSON.stringify({ paper_id: "p1", block_id: 7 }),
    },
    result: {
      type: "tool_result",
      id: "result-1",
      name: "read_paper_image",
      state: "success",
      output,
    },
  } as ToolCallWithResult
}

function pagePair(payload: Record<string, unknown>): ToolCallWithResult {
  return {
    call: {
      type: "tool_call",
      id: "call-2",
      name: "read_paper",
      input: JSON.stringify({ paper_id: "p1", page: 2 }),
    },
    result: {
      type: "tool_result",
      id: "result-2",
      name: "read_paper",
      state: "success",
      output: JSON.stringify(payload),
    },
  } as ToolCallWithResult
}

function renderBody(renderer: typeof PaperImageRenderer, pair: ToolCallWithResult) {
  const node = renderer.renderBody?.(pair, ((key: string) => key) as never)
  render(<>{node}</>)
}

function renderBodyInConversation(pair: ToolCallWithResult) {
  const openPaper = vi.fn().mockReturnValue(true)
  const node = PaperImageRenderer.renderBody?.(pair, ((key: string) => key) as never)
  render(<CitationProvider onOpen={() => {}} onOpenPaper={openPaper}>{node}</CitationProvider>)
  return openPaper
}

describe("read_paper_image rendering", () => {
  it("shows the returned picture as a data URI when the model received it", () => {
    renderBody(
      PaperImageRenderer,
      imagePair(
        { title: "Attention", page: 2, caption: "Figure 1: accuracy" },
        { data: PNG, media_type: "image/png" },
      ),
    )

    const image = screen.getByRole("img", { name: "Figure 1: accuracy" })
    expect(image.getAttribute("src")).toBe(`data:image/png;base64,${PNG}`)
    expect(screen.getByText(/Figure 1: accuracy · 第 2 页/)).toBeTruthy()
  })

  it("opens the shared large-image viewer when the picture is clicked", async () => {
    const user = userEvent.setup()
    renderBody(
      PaperImageRenderer,
      imagePair(
        { title: "Attention", page: 2, caption: "Figure 1: accuracy" },
        { data: PNG, media_type: "image/png" },
      ),
    )

    await user.click(screen.getByRole("button", { name: /查看大图/ }))

    expect(await screen.findByRole("dialog", { name: "Figure 1: accuracy" })).toBeTruthy()
  })

  it("locates the figure in the conversation reader from the call arguments", async () => {
    const user = userEvent.setup()
    const openPaper = renderBodyInConversation(
      imagePair(
        { title: "Attention", page: 2, caption: "Figure 1: accuracy" },
        { data: PNG, media_type: "image/png" },
      ),
    )

    await user.click(screen.getByRole("button", { name: "定位原文" }))

    expect(openPaper).toHaveBeenCalledWith({
      kind: "parsed_block",
      user_paper_id: "p1",
      page: 2,
      block_id: 7,
    })
  })

  it("offers no locator outside a conversation", () => {
    renderBody(
      PaperImageRenderer,
      imagePair(
        { title: "Attention", page: 2, caption: "Figure 1: accuracy" },
        { data: PNG, media_type: "image/png" },
      ),
    )

    expect(screen.queryByRole("button", { name: "定位原文" })).toBeNull()
  })

  it("explains the missing picture when the model cannot view images", () => {
    renderBody(
      PaperImageRenderer,
      imagePair({
        title: "Attention",
        page: 2,
        caption: "Figure 1: accuracy",
        note: "The current model cannot view images, so only the caption and page are provided.",
      }),
    )

    expect(screen.queryByRole("img")).toBeNull()
    expect(screen.getByText(/cannot view images/)).toBeTruthy()
    expect(screen.getByText(/Figure 1: accuracy/)).toBeTruthy()
  })
})

describe("read_paper rendering", () => {
  it("renders the page text instead of the raw tool payload", () => {
    renderBody(
      PaperPageRenderer,
      pagePair({
        title: "Attention",
        page: 2,
        total_pages: 4,
        markdown: "Second page body",
        images: [{ block_id: 7, caption: "Figure 1" }],
        truncated: true,
        partial_block_id: null,
        omitted_block_ids: [],
      }),
    )

    expect(screen.getByText(/Second page body/)).toBeTruthy()
    expect(screen.getByText(/第 7 块/)).toBeTruthy()
    expect(screen.getByText(/超出单次读取上限/)).toBeTruthy()
    expect(screen.queryByText(/"total_pages"/)).toBeNull()
  })
})
