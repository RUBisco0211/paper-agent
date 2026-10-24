// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import { expect, it } from "vitest"
import type { ToolCallWithResult } from "@/components/chat/toolRenderers/types"
import { PaperSearchRenderer } from "@/components/chat/toolRenderers/PaperSearchRenderer"

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
  expect(screen.getByText("请检查查询向量化服务是否可用")).toBeTruthy()
})

it("tells the user to check the query embedding service when results are partial", () => {
  const pair = {
    call: { id: "call-1", name: "search_papers" },
    result: {
      state: "success",
      output: JSON.stringify({
        status: "degraded",
        evidence: [{ citation_id: "cit_1", snippet: "attention", page_start: 1 }],
      }),
    },
  } as ToolCallWithResult
  render(PaperSearchRenderer.renderBody!(pair, (key) => key))

  expect(screen.getByText("请检查查询向量化服务是否可用")).toBeTruthy()
  expect(screen.queryByText(/仅使用可用通道/)).toBeNull()
})
