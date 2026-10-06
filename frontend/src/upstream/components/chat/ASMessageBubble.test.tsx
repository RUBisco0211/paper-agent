// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import type { Msg } from "@agentscope-ai/agentscope/message"
import { ReplyFinishedReason } from "@agentscope-ai/agentscope/event"
import { expect, it } from "vitest"

import i18n from "@upstream/i18n"
import { ASMessageBubble } from "./ASMessageBubble"

it("marks a retained assistant reply as stopped when its finish reason is interrupted", () => {
  void i18n.changeLanguage("zh")
  const message = {
    id: "reply-1",
    role: "assistant",
    content: [],
    created_at: "2026-10-06T00:00:00Z",
    finished_at: "2026-10-06T00:00:04Z",
    finished_reason: ReplyFinishedReason.INTERRUPTED,
  } as unknown as Msg

  render(<ASMessageBubble message={message} onUserConfirm={() => {}} />)

  expect(screen.getByText("已停止")).toBeTruthy()
})
