// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import type { SessionRecord } from "@/types/agent"
import { PaperChatPage } from "@/pages/chat/PaperChatPage"

const scroller = vi.hoisted(() => ({ scrollToEnd: vi.fn(), scrollToStart: vi.fn(), scrollToMessage: vi.fn() }))
vi.mock("@/components/ui/MessageScroller", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/ui/MessageScroller")>()
  return { ...actual, useMessageScroller: () => scroller }
})

const send = vi.hoisted(() => vi.fn(async () => true))
vi.mock("@/hooks/useMessages", () => ({
  useMessages: () => ({
    msgs: [], loading: false, phase: "idle", error: null, reconnecting: false,
    historyInterrupted: false, send, interrupt: vi.fn(), onUserConfirm: vi.fn(), onExternalAnswer: vi.fn(),
  }),
}))
vi.mock("@/components/providers/ApiProvider", () => ({
  useApi: () => ({
    api: {
      sessions: { llmCatalog: async () => ({ providers: [] }) },
      library: { list: async () => ({ items: [] }) },
      client: { request: async () => ({}) },
    },
  }),
}))
vi.mock("@/components/providers/ImportQueueProvider", () => ({ useImportQueue: () => ({ setOpen: vi.fn() }) }))
vi.mock("@/lib/agentSessions", () => ({
  availableChatModels: async () => [],
  listBindings: async () => [],
  sameSessionId: (left: string, right: string) => left === right,
}))
vi.mock("@/components/chat/MessageBubble", () => ({ MessageBubble: () => null }))
vi.mock("@/components/chat/TextInput", () => ({
  TextInput: ({ onSend }: { onSend: (blocks: Array<{ type: "text"; text: string }>) => Promise<boolean> }) =>
    <button onClick={() => void onSend([{ type: "text", text: "继续提问" }])}>发送</button>,
}))

it("follows the new message to the end when the session sends one", async () => {
  scroller.scrollToEnd.mockClear()
  const user = userEvent.setup()
  const run = {
    id: "run-1", agent_id: "agent-1", source_schedule_id: "task-1",
    config: { name: "问候", chat_model_config: { type: "deepseek_credential", credential_id: "credential-1", model: "deepseek-chat", parameters: {} } },
  }
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <PaperChatPage scheduledRun={run as SessionRecord} scheduledScope="全局" />
      </MemoryRouter>
    </QueryClientProvider>,
  )

  await user.click(screen.getByRole("button", { name: "发送" }))

  expect(send).toHaveBeenCalledTimes(1)
  expect(scroller.scrollToEnd).toHaveBeenCalledWith({ behavior: "smooth" })
})
