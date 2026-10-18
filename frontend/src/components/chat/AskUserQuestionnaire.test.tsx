// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AskUserQuestionnaire, parseAskUserQuestions } from "./AskUserQuestionnaire"

const toolCall = {
  type: "tool_call" as const,
  name: "ask_user",
  id: "call-1",
  input: JSON.stringify({ questions: [{
    name: "scope", prompt: "检索哪个范围？", type: "single",
    options: [{ value: "global", label: "全局" }, { value: "project", label: "当前项目" }],
  }] }),
  state: "submitted" as const,
  created_at: "2026-10-09T00:00:00Z",
}

describe("ask-user questionnaire", () => {
  it("submits the selected answer for the pending tool call", async () => {
    const onAnswer = vi.fn(async () => {})
    render(<AskUserQuestionnaire toolCall={toolCall} onAnswer={onAnswer} />)

    await userEvent.click(screen.getByText("当前项目"))
    await userEvent.click(screen.getByRole("button", { name: "提交答案" }))

    expect(onAnswer).toHaveBeenCalledWith({ scope: "project" })
  })

  it("rejects a repeated question name", () => {
    const input = JSON.stringify({ questions: [
      { name: "scope", prompt: "范围？", type: "text" },
      { name: "scope", prompt: "范围？", type: "text" },
    ] })
    expect(parseAskUserQuestions(input)).toEqual([])
  })

  it("submits multiple selections and a freeform answer together", async () => {
    const onAnswer = vi.fn(async () => {})
    const questions = { ...toolCall, input: JSON.stringify({ questions: [
      { name: "sources", prompt: "选择来源", type: "multiple", options: [
        { value: "library", label: "文献库" }, { value: "web", label: "网络" },
      ] },
      { name: "goal", prompt: "说明目标", type: "text" },
    ] }) }
    render(<AskUserQuestionnaire toolCall={questions} onAnswer={onAnswer} />)

    await userEvent.click(screen.getByText("文献库"))
    await userEvent.click(screen.getByText("网络"))
    await userEvent.click(screen.getByRole("button", { name: "下一题" }))
    await userEvent.type(screen.getByRole("textbox", { name: "填写答案" }), "比较方法")
    await userEvent.click(screen.getByRole("button", { name: "提交答案" }))

    expect(onAnswer).toHaveBeenCalledWith({ sources: ["library", "web"], goal: "比较方法" })
  })
})
