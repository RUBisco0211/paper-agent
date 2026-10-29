// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { AssistantMsg, UserMsg } from "@agentscope-ai/agentscope/message"
import { expect, it, vi } from "vitest"

import { MessageNavigationRail } from "@/components/chat/MessageNavigationRail"

const scrollToMessage = vi.fn(() => true)
vi.mock("@/components/ui/MessageScroller", () => ({
  useMessageScroller: () => ({ scrollToMessage }),
  useMessageScrollerVisibility: () => ({ currentAnchorId: null, visibleMessageIds: ["answer-1"] }),
}))

it("marks only the questions, never the answers", () => {
  const messages = [
    UserMsg({ id: "question-1", name: "user", content: "请总结这篇文献的主要发现", metadata: {} }),
    AssistantMsg({ id: "answer-1", name: "assistant", content: "主要发现包括三个方面。", metadata: {} }),
    UserMsg({ id: "question-2", name: "user", content: "那局限呢", metadata: {} }),
    AssistantMsg({ id: "answer-2", name: "assistant", content: "局限在于样本量。", metadata: {} }),
  ]
  render(<MessageNavigationRail messages={messages} />)

  const marks = screen.getAllByRole("button", { name: /跳转到第/ })
  expect(marks).toHaveLength(2)
  expect(marks[0].getAttribute("aria-label")).toBe("跳转到第 1 个提问")
  expect(marks[1].getAttribute("aria-label")).toBe("跳转到第 2 个提问")
})

it("previews and locates a question when its rail mark is used", async () => {
  scrollToMessage.mockClear()
  const user = userEvent.setup()
  const messages = [
    UserMsg({ id: "question-1", name: "user", content: "请总结这篇文献的主要发现", metadata: {} }),
    AssistantMsg({ id: "answer-1", name: "assistant", content: "主要发现包括三个方面。", metadata: {} }),
    UserMsg({ id: "question-2", name: "user", content: "那局限呢", metadata: {} }),
  ]
  render(<MessageNavigationRail messages={messages} />)
  const marks = screen.getAllByRole("button", { name: /跳转到第/ })

  await user.hover(marks[0])
  expect(await screen.findByText("请总结这篇文献的主要发现")).toBeTruthy()
  // 回复不进导航，所以它的正文不会作为标记出现。
  expect(screen.queryByText("主要包括三个方面。")).toBeNull()
  await user.click(marks[0])
  expect(scrollToMessage).toHaveBeenCalledWith("question-1", { align: "start", behavior: "smooth" })
})

it("stays hidden when the conversation holds a single question", () => {
  const messages = [
    UserMsg({ id: "question-1", name: "user", content: "只有一个提问", metadata: {} }),
    AssistantMsg({ id: "answer-1", name: "assistant", content: "一个回答", metadata: {} }),
  ]
  const { container } = render(<MessageNavigationRail messages={messages} />)
  expect(container.querySelector("nav")).toBeNull()
})

it("aligns each preview mark to the same width when expanded", async () => {
  const user = userEvent.setup()
  const messages = [
    UserMsg({ id: "question-1", name: "user", content: "第一条提问", metadata: {} }),
    AssistantMsg({ id: "answer-1", name: "assistant", content: "第一条回答", metadata: {} }),
    UserMsg({ id: "question-2", name: "user", content: "第二条提问", metadata: {} }),
  ]
  render(<MessageNavigationRail messages={messages} />)
  const first = screen.getByRole("button", { name: "跳转到第 1 个提问" })
  const second = screen.getByRole("button", { name: "跳转到第 2 个提问" })
  expect(first.querySelector("span")?.className).toContain("w-2")
  expect(second.querySelector("span")?.className).toContain("w-2")

  await user.hover(first)

  expect(first.textContent).toContain("第一条提问")
  expect(second.textContent).toContain("第二条提问")
})
