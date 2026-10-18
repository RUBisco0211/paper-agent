// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import { expect, it } from "vitest"

import { AskUserRenderer } from "./AskUserRenderer"
import type { ToolCallWithResult } from "./types"

it("shows submitted answers under their questions when an ask-user call finishes", () => {
  const pair = {
    call: { name: "ask_user", input: JSON.stringify({ questions: [
      { name: "scope", prompt: "检索范围？", type: "single", options: [{ value: "project", label: "当前项目" }, { value: "global", label: "全局" }] },
      { name: "sources", prompt: "需要哪些来源？", type: "multiple", options: [{ value: "paper", label: "文献" }, { value: "web", label: "网页" }] },
      { name: "note", prompt: "补充说明？", type: "text" },
    ] }) },
    result: { state: "success", output: JSON.stringify({ answers: { scope: "project", sources: ["paper", "web"], note: null } }) },
  } as ToolCallWithResult

  render(<>{AskUserRenderer.renderBody!(pair, (key) => key)}</>)
  expect(screen.getByText("1. 检索范围？")).toBeTruthy()
  expect(screen.getByText("2. 需要哪些来源？")).toBeTruthy()
  expect(screen.getByText("3. 补充说明？")).toBeTruthy()
  expect(screen.getByText("当前项目")).toBeTruthy()
  expect(screen.getByText("文献、网页")).toBeTruthy()
  expect(screen.getByText("已跳过")).toBeTruthy()
  expect(screen.queryByText("已提交答案")).toBeNull()
})
