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

  it("shows the stable code, not the message, when search could not run", () => {
    const body = WebSearchRenderer.renderBody!(
      pair(
        "web_search",
        '{"query":"RSC"}',
        JSON.stringify({
          status: "error",
          code: "provider_not_configured",
          message: "api key unavailable",
        }),
      ),
      t,
    )
    render(<>{body}</>)
    expect(screen.getByRole("alert").textContent).toBe("provider_not_configured")
    expect(screen.queryByText("no results")).toBeNull()
  })

  it("falls back to a stable code when the tool result carries none", () => {
    const body = WebSearchRenderer.renderBody!(
      pair("web_search", "{}", JSON.stringify({ status: "error" })),
      t,
    )
    render(<>{body}</>)
    expect(screen.getByRole("alert").textContent).toBe("provider_unavailable")
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

  it("shows the code when a page could not be read", () => {
    const body = WebFetchRenderer.renderBody!(
      pair(
        "web_fetch",
        '{"url":"https://example.org/page"}',
        JSON.stringify({
          status: "error",
          code: "provider_unavailable",
          message: "page not readable",
        }),
      ),
      t,
    )
    render(<>{body}</>)
    expect(screen.getByRole("alert").textContent).toBe("provider_unavailable")
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
    expect(screen.getByText("offset out of range")).toBeTruthy()
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
    expect(screen.getByText("excerpt only")).toBeTruthy()
  })
})
