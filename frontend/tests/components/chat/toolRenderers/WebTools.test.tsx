// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { WebFetchRenderer, WebExcerptRenderer } from "@/components/chat/toolRenderers/WebPageRenderer"
import { WebSearchRenderer } from "@/components/chat/toolRenderers/WebSearchRenderer"
import type { ToolCallWithResult } from "@/components/chat/toolRenderers/types"

function pair(name: string, input: string, text: string, state = "success"): ToolCallWithResult {
  return {
    call: { name, input } as ToolCallWithResult["call"],
    result: { state, output: [{ type: "text", text }] } as unknown as ToolCallWithResult["result"],
  }
}

const t = (key: string) => key

describe("web tool rendering", () => {
  it("lists search hits as links the user can open", () => {
    const body = WebSearchRenderer.renderBody!(
      pair(
        "web_search",
        '{"query":"RSC"}',
        JSON.stringify({
          status: "ok",
          results: [
            {
              title: "Reflected Self-Consistency",
              url: "https://arxiv.org/abs/2401.00001",
              snippet: "A decoding method.",
            },
          ],
        }),
      ),
      t,
    )
    render(<>{body}</>)
    const link = screen.getByRole("link", { name: /Reflected Self-Consistency/ })
    expect(link.getAttribute("href")).toBe("https://arxiv.org/abs/2401.00001")
    expect(link.getAttribute("target")).toBe("_blank")
    expect(screen.getByText("A decoding method.")).toBeTruthy()
  })

  it("shows one plain error for every failure reason", () => {
    const codes = ["provider_not_configured", "rate_limited", "provider_unavailable"]
    const alerts = codes.map((code) => {
      const body = WebSearchRenderer.renderBody!(
        pair("web_search", '{"query":"RSC"}', JSON.stringify({ status: "error", code })),
        t,
      )
      return render(<>{body}</>).container.textContent
    })
    expect(new Set(alerts).size).toBe(1)
    expect(alerts[0]).toBe("工具调用错误")
  })

  it("truncates a long search snippet before it reaches the page", () => {
    const snippet = "x".repeat(900)
    const body = WebSearchRenderer.renderBody!(
      pair(
        "web_search",
        "{}",
        JSON.stringify({
          status: "ok",
          results: [{ title: "Hit", url: "https://a.example", snippet }],
        }),
      ),
      t,
    )
    render(<>{body}</>)
    const rendered = screen.getByText(/^x+…$/).textContent ?? ""
    expect(rendered.length).toBeLessThan(300)
  })

  it("links a fetched page back to its source and shows the text", () => {
    const body = WebFetchRenderer.renderBody!(
      pair(
        "web_fetch",
        '{"url":"https://example.org/page"}',
        JSON.stringify({
          status: "ok",
          url: "https://example.org/page",
          content: "page body text",
          truncated: true,
          next_offset: 10,
          offset_out_of_range: false,
        }),
      ),
      t,
    )
    render(<>{body}</>)
    expect(screen.getByRole("link", { name: "example.org" }).getAttribute("href")).toBe(
      "https://example.org/page",
    )
    expect(screen.getByText("page body text")).toBeTruthy()
  })

  it("says so when a read started past the end of the page", () => {
    const body = WebFetchRenderer.renderBody!(
      pair(
        "web_fetch",
        '{"url":"https://example.org/page"}',
        JSON.stringify({
          status: "ok",
          url: "https://example.org/page",
          content: "",
          truncated: false,
          next_offset: null,
          total_chars: 40,
          offset_out_of_range: true,
        }),
      ),
      t,
    )
    render(<>{body}</>)
    expect(screen.getByText("已读到页面末尾")).toBeTruthy()
  })

  it("marks an excerpt read so the user knows it is not the whole page", () => {
    const body = WebExcerptRenderer.renderBody!(
      pair(
        "web_extract_excerpt",
        '{"url":"https://example.org/page","query":"what is RSC"}',
        JSON.stringify({
          status: "ok",
          url: "https://example.org/page",
          content: "passage",
          excerpt_only: true,
        }),
      ),
      t,
    )
    render(<>{body}</>)
    expect(screen.getByText("以下是与问题相关的摘录")).toBeTruthy()
  })
})
