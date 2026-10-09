// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { ApiError } from "@upstream/api/client"
import type { ToolCallBlock } from "@agentscope-ai/agentscope/message"

const api = vi.hoisted(() => ({
  messages: vi.fn(),
  streamEvents: vi.fn(),
  trigger: vi.fn(),
}))

vi.mock("@upstream/api", () => ({
  sessionApi: api,
  chatApi: { trigger: api.trigger },
  takeFreshlyCreated: () => false,
}))

import { useMessages } from "./useMessages"

beforeEach(() => vi.clearAllMocks())

it("reconnects the event stream when the connection drops", async () => {
  api.messages.mockResolvedValue({ messages: [], is_running: false })
  api.streamEvents.mockImplementation(async function* () {
    throw new Error("connection closed")
  })

  const { unmount } = renderHook(() => useMessages("agent-1", "session-1"))

  await waitFor(() => expect(api.streamEvents).toHaveBeenCalledTimes(2), {
    timeout: 2500,
  })
  unmount()
})

it("shows a reconnecting state while a transient stream failure is being retried", async () => {
  api.messages.mockResolvedValue({ messages: [], is_running: false })
  api.streamEvents.mockImplementation(async function* () {
    throw new Error("connection closed")
  })

  const { result, unmount } = renderHook(() => useMessages("agent-1", "session-1"))
  await waitFor(() => expect(result.current.reconnecting).toBe(true))
  expect(result.current.error).toBeNull()
  unmount()
})

it("reports an unfinished answer when history ends with a user message after restart", async () => {
  api.messages.mockResolvedValue({
    messages: [{ id: "user-1", role: "user", content: [] }],
    is_running: false,
  })
  api.streamEvents.mockImplementation(async function* () {
    await new Promise(() => {})
  })

  const { result, unmount } = renderHook(() => useMessages("agent-1", "session-1"))

  await waitFor(() => expect(result.current.loading).toBe(false))
  expect(result.current.historyInterrupted).toBe(true)
  unmount()
})

it("does not retry a stream for a deleted session", async () => {
  api.messages.mockResolvedValue({ messages: [], is_running: false })
  api.streamEvents.mockImplementation(async function* () {
    throw new ApiError(404, "Session not found")
  })

  const { unmount } = renderHook(() => useMessages("agent-1", "session-1"))
  await waitFor(() => expect(api.streamEvents).toHaveBeenCalledTimes(1))
  await new Promise((resolve) => setTimeout(resolve, 1200))
  expect(api.streamEvents).toHaveBeenCalledTimes(1)
  unmount()
})

it("returns an ask-user answer as an external result for the same reply", async () => {
  api.messages.mockResolvedValue({ messages: [{
    id: "reply-1", role: "assistant", name: "Reader", metadata: {},
    created_at: "2026-10-09T00:00:00Z", content: [{
      type: "tool_call", id: "call-1", name: "ask_user", input: "{}",
      state: "submitted", created_at: "2026-10-09T00:00:00Z",
    }],
  }], is_running: true })
  api.streamEvents.mockImplementation(async function* () {
    await new Promise(() => {})
  })
  api.trigger.mockResolvedValue({ status: "accepted" })
  const { result, unmount } = renderHook(() => useMessages("agent-1", "session-1"))
  await waitFor(() => expect(result.current.loading).toBe(false))

  await act(async () => {
    await result.current.onExternalAnswer(result.current.msgs[0].content[0] as ToolCallBlock, "reply-1", { scope: "project" })
  })

  const request = api.trigger.mock.calls[0][0]
  expect(request.session_id).toBe("session-1")
  expect(request.input.reply_id).toBe("reply-1")
  expect(request.input.type).toBe("EXTERNAL_EXECUTION_RESULT")
  expect(request.input.execution_results[0]).toMatchObject({
    id: "call-1", name: "ask_user", state: "success",
    output: JSON.stringify({ answers: { scope: "project" } }),
  })
  unmount()
})
