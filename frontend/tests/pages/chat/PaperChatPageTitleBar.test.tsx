// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { PaperChatPage } from "@/pages/chat/PaperChatPage"

vi.mock("@/lib/api/agentscope/session", () => ({
  sessionApi: {
    list: async () => ({
      sessions: [{ session: { id: "session-1", config: { name: "DGPPO 论文解读" } } }],
    }),
  },
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
vi.mock("@/components/providers/ImportQueueProvider", () => ({
  useImportQueue: () => ({ setOpen: vi.fn() }),
}))
vi.mock("@/lib/agentSessions", () => ({
  availableChatModels: async () => [],
  listBindings: async () => [],
  sameSessionId: (left: string, right: string) => left === right,
}))
vi.mock("@/hooks/useMessages", () => ({
  useMessages: () => ({
    msgs: [], loading: false, phase: "idle", error: null, reconnecting: false,
    historyInterrupted: false, send: vi.fn(), interrupt: vi.fn(),
    onUserConfirm: vi.fn(), onExternalAnswer: vi.fn(),
  }),
}))
vi.mock("@/components/chat/MessageBubble", () => ({ MessageBubble: () => null }))
vi.mock("@/components/chat/TextInput", () => ({ TextInput: () => null }))

it("shows the session title in the main column's own title bar", async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={["/chat/agent-1/session-1"]}>
        <Routes>
          <Route path="/chat/:agentId/:sessionId" element={<PaperChatPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )

  const bar = await screen.findByLabelText("会话标题")
  await waitFor(() => expect(bar.textContent).toBe("DGPPO 论文解读"))
  // Same height token as the papers panel's bar, so the two bottom edges meet.
  expect(bar.classList.contains("h-(--app-toolbar-height)")).toBe(true)
})
