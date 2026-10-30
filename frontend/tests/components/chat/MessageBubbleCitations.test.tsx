// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { Msg } from "@agentscope-ai/agentscope/message"
import { expect, it, vi } from "vitest"

import "@/i18n"
import { CitationProvider } from "@/components/chat/CitationProvider"
import { MessageBubble } from "@/components/chat/MessageBubble"

const cited = "cit_0123456789ab"
const invented = "cit_ffffffffffff"

function answer(text: string): Msg {
  return {
    id: "reply-1",
    role: "assistant",
    content: [{ id: "block-1", type: "text", text, created_at: "2026-10-30T00:00:00Z", finished_at: "2026-10-30T00:00:04Z" }],
    created_at: "2026-10-30T00:00:00Z",
    finished_at: "2026-10-30T00:00:04Z",
  } as unknown as Msg
}

function renderAnswer(text: string, known: string[], onOpen = vi.fn()) {
  render(
    <CitationProvider onOpen={onOpen}>
      <MessageBubble message={answer(text)} registeredCitations={new Set(known)} onUserConfirm={() => {}} />
    </CitationProvider>,
  )
  return { onOpen }
}

it("turns a registered citation marker into a numbered chip", () => {
  const { onOpen } = renderAnswer(`结论是安全的 [${cited}]。`, [cited])

  const chip = screen.getByRole("button", { name: "[1]" })
  expect(chip).toBeTruthy()
  expect(screen.queryByText(cited, { exact: false })).toBeNull()
  expect(onOpen).not.toHaveBeenCalled()
})

it("opens the citation only when the chip is clicked", async () => {
  const user = userEvent.setup()
  const { onOpen } = renderAnswer(`结论是安全的 [${cited}]。`, [cited])

  await user.click(screen.getByRole("button", { name: "[1]" }))

  expect(onOpen).toHaveBeenCalledWith(cited)
})

it("leaves a marker the session never registered as plain text", () => {
  renderAnswer(`结论 [${invented}]`, [cited])

  expect(screen.queryByRole("button", { name: /^\[/ })).toBeNull()
  expect(screen.getByText(invented, { exact: false })).toBeTruthy()
})
