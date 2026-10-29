// @vitest-environment jsdom
import { render } from "@testing-library/react"
import type { Msg } from "@agentscope-ai/agentscope/message"
import { expect, it } from "vitest"

import "@/i18n"
import { MessageBubble } from "@/components/chat/MessageBubble"

const mention = {
  index: 1,
  user_paper_id: "p-1",
  title: "Safe and Scalable Payload Transport",
  has_fulltext: true,
}

function userMessage(text: string, mentions: unknown[] = [mention]) {
  return {
    id: "user-1",
    role: "user",
    content: [{ id: "block-1", type: "text", text, created_at: "2026-10-30T00:00:00Z" }],
    created_at: "2026-10-30T00:00:00Z",
    finished_at: "2026-10-30T00:00:00Z",
    metadata: { paper_agent: { body: text, mentions } },
  } as unknown as Msg
}

function mentionBadge(container: HTMLElement) {
  return container.querySelector<HTMLElement>('[data-slot="badge"]')
}

it("renders a recorded mention as a badge instead of the raw paper marker", () => {
  const { container } = render(
    <MessageBubble
      message={userMessage("对比 @《Safe and Scalable Payload Transport》(paper:p-1) 和正文")}
      onUserConfirm={() => {}}
    />,
  )

  expect(mentionBadge(container)?.textContent).toBe("@Safe and Scalable Payloa…")
  expect(container.textContent).not.toContain("paper:p-1")
  expect(container.textContent).not.toContain("《")
})

it("gives the mention the same outline chrome as a reference badge", () => {
  const { container } = render(
    <MessageBubble
      message={userMessage("对比 @《Safe and Scalable Payload Transport》(paper:p-1) 和正文")}
      onUserConfirm={() => {}}
    />,
  )

  const badge = mentionBadge(container)
  expect(badge?.dataset.variant).toBe("outline")
  expect(badge?.className).toContain("border-(--message-quote-accent)")
  expect(badge?.className).toContain("max-w-64")
})

it("drops the pending-fulltext hint the service adds for the model", () => {
  const { container } = render(
    <MessageBubble
      message={userMessage("讲讲 @《Safe and Scalable Payload Transport》(paper:p-1)（待补全文）")}
      onUserConfirm={() => {}}
    />,
  )

  expect(mentionBadge(container)?.textContent).toBe("@Safe and Scalable Payloa…")
  expect(container.textContent).not.toContain("待补全文")
})

it("leaves a message without recorded mentions untouched", () => {
  const { container } = render(
    <MessageBubble
      message={userMessage("对比 @《Safe and Scalable Payload Transport》(paper:p-1) 和正文", [])}
      onUserConfirm={() => {}}
    />,
  )

  expect(mentionBadge(container)).toBeNull()
  expect(container.textContent).toContain("@《Safe and Scalable Payload Transport》(paper:p-1)")
})

it("chips the readable token of the message this tab just sent", () => {
  const { container } = render(
    <MessageBubble
      message={userMessage("对比 @Safe and Scalable Payload Transport 和正文", [
        { index: 1, user_paper_id: "p-1", title: "Safe and Scalable Payload Transport" },
      ])}
      onUserConfirm={() => {}}
    />,
  )

  expect(mentionBadge(container)?.textContent).toBe("@Safe and Scalable Payloa…")
  expect(container.textContent).not.toContain("@Safe and Scalable Payload Transport")
})
