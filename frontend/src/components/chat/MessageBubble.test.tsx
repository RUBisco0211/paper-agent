// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react"
import type { Msg } from "@agentscope-ai/agentscope/message"
import { ReplyFinishedReason } from "@agentscope-ai/agentscope/event"
import { expect, it, vi } from "vitest"

import i18n from "@/i18n"
import { MessageBubble } from "./MessageBubble"
import { messageQuoteKey } from "./quoteReferences"

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

  render(<MessageBubble message={message} onUserConfirm={() => {}} />)

  expect(screen.getByText("已停止")).toBeTruthy()
})

it("copies the assistant reply text when its copy action is clicked", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } })
  render(<MessageBubble message={{ id: "reply-2", role: "assistant", content: [{ type: "text", text: "**Answer**" }], created_at: "2026-10-06T00:00:00Z", finished_at: "2026-10-06T00:00:04Z" } as unknown as Msg} onUserConfirm={() => {}} />)
  fireEvent.click(screen.getByRole("button", { name: "复制消息" }))
  expect(writeText).toHaveBeenCalledWith("**Answer**")
})

it("shows only a copy action for a user message", () => {
  render(<MessageBubble message={{ id: "user-1", role: "user", content: [{ type: "text", text: "Hello" }], created_at: "2026-10-06T00:00:00Z", finished_at: "2026-10-06T00:00:00Z" } as unknown as Msg} onUserConfirm={() => {}} />)
  expect(screen.getByRole("button", { name: "复制消息" })).toBeTruthy()
  expect(screen.queryByRole("button", { name: "导出 Markdown" })).toBeNull()
})

it("shows the reply finish time after assistant actions", () => {
  render(<MessageBubble message={{ id: "reply-3", role: "assistant", content: [{ type: "text", text: "Done" }], created_at: new Date(2026, 9, 6, 8, 0).toISOString(), finished_at: new Date(2026, 9, 6, 8, 3).toISOString() } as unknown as Msg} onUserConfirm={() => {}} />)
  expect(screen.getByText("08:03")).toBeTruthy()
})

it("shows the send time after user actions", () => {
  render(<MessageBubble message={{ id: "user-2", role: "user", content: [{ type: "text", text: "Hello" }], created_at: new Date(2026, 9, 6, 8, 0).toISOString(), finished_at: new Date(2026, 9, 6, 8, 2).toISOString() } as unknown as Msg} onUserConfirm={() => {}} />)
  expect(screen.getByText("08:00")).toBeTruthy()
})

it("shows only the selected historical inline comment", async () => {
  const message = { id: "reply-quote", role: "assistant", content: [{ type: "text", text: "**same** text and same text", id: "block-1" }], created_at: "2026-10-06T00:00:00Z", finished_at: "2026-10-06T00:00:04Z" } as unknown as Msg
  const annotations = [{ kind: "message" as const, source_message_id: "reply-quote", block_index: 0, start: 14, end: 18, selected_text: "same", comment: "第二次出现" }]
  const { rerender } = render(<MessageBubble message={message} annotations={annotations} onUserConfirm={() => {}} />)
  expect(screen.queryByLabelText("引用评论")).toBeNull()
  rerender(<MessageBubble message={message} annotations={annotations} activeAnnotationKey={messageQuoteKey(annotations[0])} onUserConfirm={() => {}} />)
  expect((await screen.findByLabelText("引用评论")).textContent).toBe("第二次出现")
  rerender(<MessageBubble message={message} annotations={annotations} activeAnnotationKey={null} onUserConfirm={() => {}} />)
  expect(screen.queryByLabelText("引用评论")).toBeNull()
})

it.each([
  { shortcut: 'Ctrl+Enter', modifier: { ctrlKey: true } },
  { shortcut: 'Meta+Enter', modifier: { metaKey: true } },
])("opens focused comment editing and submits with $shortcut after comment is chosen", async ({ modifier }) => {
  const message = { id: "reply-menu", role: "assistant", content: [{ type: "text", text: "hello world", id: "block-menu" }], created_at: "2026-10-06T00:00:00Z", finished_at: "2026-10-06T00:00:04Z" } as unknown as Msg
  const onQuote = vi.fn().mockReturnValue(true)
  const { container } = render(<MessageBubble message={message} onUserConfirm={() => {}} onQuote={onQuote} />)
  const root = container.querySelector<HTMLElement>('[data-quote-block-index="0"]')!
  const walker = document.createTreeWalker(root.querySelector('p')!, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  while (walker.nextNode()) nodes.push(walker.currentNode as Text)
  const text = nodes.at(-1)!
  const range = document.createRange()
  range.setStart(text, text.length - 5)
  range.setEnd(text, text.length)
  window.getSelection()?.removeAllRanges()
  window.getSelection()?.addRange(range)
  expect(screen.queryByLabelText('引用评论')).toBeNull()
  fireEvent.contextMenu(root)
  expect(screen.getByRole('menuitem', { name: '复制' }).querySelector('svg')).toBeTruthy()
  fireEvent.click(screen.getByRole('menuitem', { name: '评论' }))
  const input = await screen.findByLabelText('引用评论')
  expect(document.activeElement).toBe(input)
  fireEvent.change(input, { target: { value: '为什么？' } })
  fireEvent.keyDown(input, { key: 'Enter' })
  expect(onQuote).not.toHaveBeenCalled()
  fireEvent.keyDown(input, { key: 'Enter', ...modifier })
  expect(onQuote).toHaveBeenCalledWith({ kind: 'message', source_message_id: 'reply-menu', block_index: 0, start: 6, end: 11, selected_text: 'world', comment: '为什么？' })
})
