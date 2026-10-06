// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import { expect, it } from "vitest"
import type { ToolCallWithResult } from "./types"
import { PaperSearchRenderer } from "./PaperSearchRenderer"

function showSearchResult(status: string, state: "success" | "error" = "success") {
  const pair = {
    call: { id: "call-1", name: "search_papers" },
    result: { state, output: JSON.stringify({ status, evidence: [] }) },
  } as ToolCallWithResult
  render(PaperSearchRenderer.renderBody!(pair, (key) => key))
}

it("reports retrieval failure when the search tool is unavailable", () => {
  showSearchResult("unavailable")
  expect(screen.getByText("检索暂不可用，请重试")).toBeTruthy()
  expect(screen.queryByText("没有可引用的文献片段")).toBeNull()
})

it("reports no evidence when search completed without a match", () => {
  showSearchResult("ok")
  expect(screen.getByText("没有可引用的文献片段")).toBeTruthy()
})

it("marks a partial search when only a subset of channels completed", () => {
  showSearchResult("degraded")
  expect(screen.getByText("检索已降级，未找到可引用的文献片段")).toBeTruthy()
})
