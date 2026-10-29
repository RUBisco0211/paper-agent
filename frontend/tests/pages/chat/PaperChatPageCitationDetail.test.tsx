// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { act, render, screen, waitFor } from "@testing-library/react"
import { useEffect } from "react"
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { PaperChatPage } from "@/pages/chat/PaperChatPage"

const harness = vi.hoisted(() => ({
  resolvers: [] as Array<(value: unknown) => void>,
  requests: [] as string[],
}))
const openers = vi.hoisted(() => ({ current: null as null | ((id: string) => void) }))

vi.mock("@/components/chat/CitationProvider", async () => {
  const actual = await vi.importActual<typeof import("@/components/chat/CitationProvider")>(
    "@/components/chat/CitationProvider",
  )
  return {
    ...actual,
    CitationProvider: ({ onOpen, children }: { onOpen: (id: string) => void; children: React.ReactNode }) => {
      openers.current = onOpen
      return <actual.CitationProvider onOpen={onOpen}>{children}</actual.CitationProvider>
    },
  }
})

vi.mock("@/components/providers/ApiProvider", () => ({
  useApi: () => ({
    api: {
      sessions: { llmCatalog: async () => ({ providers: [] }) },
      library: { list: async () => ({ items: [] }) },
      client: {
        request: (path: string) => {
          harness.requests.push(path)
          if (!path.includes("/citations/")) return Promise.resolve({})
          return new Promise((resolve) => harness.resolvers.push(resolve))
        },
      },
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

const switcher = { current: null as null | ((sessionId: string) => void) }

function SessionSwitcher() {
  const navigate = useNavigate()
  useEffect(() => {
    switcher.current = (sessionId: string) => navigate(`/chat/${sessionId}`)
  }, [navigate])
  return null
}

function payload(snippet: string) {
  return { paper_id: "paper-1", snippet, page_start: 1, source_locations: [{ block_id: 1, page: 1 }] }
}

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={["/chat/session-a"]}>
        <Routes>
          <Route path="/chat/:sessionId" element={<PaperChatPage />} />
        </Routes>
        <SessionSwitcher />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  harness.requests.length = 0
  harness.resolvers.length = 0
  openers.current = null
})

describe("PaperChatPage citation detail", () => {
  it("keeps the citation dialog closed when a response arrives for a session the user left", async () => {
    renderPage()
    await waitFor(() => expect(openers.current).not.toBeNull())

    act(() => openers.current!("cit_a"))
    await waitFor(() => expect(harness.resolvers).toHaveLength(1))
    expect(harness.requests[0]).toContain("session-a")

    act(() => switcher.current!("session-b"))
    await waitFor(() => expect(screen.queryByText("引用详情")).toBeNull())

    await act(async () => { harness.resolvers[0](payload("旧会话的证据")) })

    expect(screen.queryByText("旧会话的证据")).toBeNull()
  })

  it("closes an open citation dialog when the user switches session", async () => {
    renderPage()
    await waitFor(() => expect(openers.current).not.toBeNull())

    act(() => openers.current!("cit_a"))
    await waitFor(() => expect(harness.resolvers).toHaveLength(1))
    await act(async () => { harness.resolvers[0](payload("当前会话的证据")) })
    expect(screen.getByText("引用详情")).toBeTruthy()

    act(() => switcher.current!("session-b"))

    await waitFor(() => expect(screen.queryByText("引用详情")).toBeNull())
  })
})
