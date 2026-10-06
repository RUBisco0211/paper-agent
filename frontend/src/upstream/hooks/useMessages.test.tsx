// @vitest-environment jsdom
import { renderHook, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { ApiError } from "@upstream/api/client"

const api = vi.hoisted(() => ({
  messages: vi.fn(),
  streamEvents: vi.fn(),
}))

vi.mock("@upstream/api", () => ({
  sessionApi: api,
  chatApi: { trigger: vi.fn() },
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
