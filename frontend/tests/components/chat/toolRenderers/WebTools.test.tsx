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

describe("web tool rendering", () => {
  it("lists search hits as links the user can open", () => {
    const body = WebSearchRenderer.renderBody!(
      pair(
        "web_search",
        '{"query":"RSC"}',
        JSON.stringify({
          status: "ok",
          results: [
            { title: "Reflected Self-Consistency", url: "https://arxiv.org/abs/2401.00001", snippet: "A decoding method." },
          ],
        }),
      ),
      (key) => key,
    )
    render(<>{body}</>)
    const link = screen.getByRole("link", { name: /Reflected Self-Consistency/ })
    expect(link.getAttribute("href")).toBe("https://arxiv.org/abs/2401.00001")
    expect(link.getAttribute("target")).toBe("_blank")
    expect(screen.getByText("A decoding method.")).toBeTruthy()
  })

  it("shows the configured-key hint when search could not run", () => {
    const body = WebSearchRenderer.renderBody!(
      pair(
        "web_search",
        "{}",
        JSON.stringify({
          status: "error",
          code: "web_search_not_configured",
          message: "尚未配置联网搜索密钥，请到设置中填写。",
        }),
        "error",
      ),
      (key) => key,
    )
    render(<>{body}</>)
    expect(screen.getByRole("alert").textContent).toContain("尚未配置联网搜索密钥")
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
        }),
      ),
      (key) => key,
    )
    render(<>{body}</>)
    expect(screen.getByRole("link", { name: "example.org" }).getAttribute("href")).toBe(
      "https://example.org/page",
    )
    expect(screen.getByText("page body text")).toBeTruthy()
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
      (key) => key,
    )
    render(<>{body}</>)
    expect(screen.getByText("以下是与该问题相关的段落摘录")).toBeTruthy()
  })
})
