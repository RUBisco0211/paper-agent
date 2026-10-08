// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { AssistantMsg, UserMsg } from "@agentscope-ai/agentscope/message"
import { expect, it, vi } from "vitest"

import { MessageNavigationRail } from "./MessageNavigationRail"

const scrollToMessage = vi.fn(() => true)
vi.mock("@upstream/components/ui/message-scroller", () => ({
  useMessageScroller: () => ({ scrollToMessage }),
  useMessageScrollerVisibility: () => ({ currentAnchorId: null, visibleMessageIds: ["answer-1"] }),
}))

it("previews and locates a message when its rail mark is used", async () => {
  scrollToMessage.mockClear()
  const user = userEvent.setup()
  const messages = [
    UserMsg({ id: "question-1", name: "user", content: "请总结这篇文献的主要发现", metadata: {} }),
    AssistantMsg({ id: "answer-1", name: "assistant", content: "主要发现包括三个方面。", metadata: {} }),
  ]
  render(<MessageNavigationRail messages={messages} />)
  const marks = screen.getAllByRole("button", { name: /跳转到第/ })
  expect(marks).toHaveLength(2)
  expect(marks[1].getAttribute("aria-current")).toBe("location")
  await user.hover(marks[0])
  expect(await screen.findByText("请总结这篇文献的主要发现")).toBeTruthy()
  await user.click(marks[0])
  expect(scrollToMessage).toHaveBeenCalledWith("question-1", { align: "start", behavior: "smooth" })
})
