// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { ChatQuoteContext } from "@/components/chat/chatQuoteContext"
import { PaperChatPage } from "@/pages/chat/PaperChatPage"

const harness = vi.hoisted(() => ({
  openers: [] as Array<(id: string) => void>,
  opened: [] as unknown[],
  sidebarOpen: true,
  path: "",
}))

vi.mock("@/components/chat/CitationProvider", async () => {
  const actual = await vi.importActual<typeof import("@/components/chat/CitationProvider")>(
    "@/components/chat/CitationProvider",
  )
  return {
    ...actual,
    CitationProvider: ({ onOpen, children }: {
      onOpen: (id: string) => void
      children: React.ReactNode
    }) => {
      harness.openers.push(onOpen)
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
        request: async (path: string) => {
          if (!path.includes("/citations/")) return {}
          return {
            paper_id: "entry-1",
            snippet: "attention evidence",
            page_start: null,
            source_locations: [{ block_id: 7, page: null }],
          }
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

function PathProbe() {
  harness.path = useLocation().pathname
  const navigate = useNavigate()
  void navigate
  return null
}


function renderWithBridge(openPaper: (reference: unknown) => boolean) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <ChatQuoteContext.Provider
        value={{
          register: () => () => {},
          add: () => true,
          registerPaperOpener: () => () => {},
          openPaper: (sessionId, reference) => {
            harness.sidebarOpen = true
            return openPaper({ ...reference, sessionId })
          },
          openEntry: () => () => {},
        }}
      >
        <MemoryRouter initialEntries={["/chat/session-a"]}>
          <Routes>
            <Route path="/chat/:sessionId" element={<PaperChatPage />} />
          </Routes>
          <PathProbe />
        </MemoryRouter>
      </ChatQuoteContext.Provider>
    </QueryClientProvider>,
  )
}

async function clickLocate() {
  const user = userEvent.setup()
  act(() => harness.openers.at(-1)?.("cit_a"))
  await user.click(await screen.findByRole("button", { name: /定位/ }))
}

describe("locating a citation block", () => {
  beforeEach(() => {
    harness.openers.length = 0
    harness.opened = []
    harness.sidebarOpen = false
    harness.path = ""
  })

  it("lands in the conversation sidebar with the block instead of the library page", async () => {
    renderWithBridge((reference) => {
      harness.opened.push(reference)
      return true
    })

    await waitFor(() => expect(harness.openers.length).toBeGreaterThan(0))
    await clickLocate()

    expect(harness.opened[0]).toEqual(expect.objectContaining({
      kind: "parsed_block", user_paper_id: "entry-1", block_id: 7,
    }))
    expect(harness.path).toBe("/chat/session-a")
    // A collapsed sidebar is expanded so the reader is actually visible.
    expect(harness.sidebarOpen).toBe(true)
  })

  it("falls back to the library page only when no sidebar can take the block", async () => {
    cleanup()
    harness.openers = []
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter initialEntries={["/chat/session-a"]}>
          <Routes>
            <Route path="/chat/:sessionId" element={<PaperChatPage />} />
            <Route path="/library/:paperId" element={<p>library page</p>} />
          </Routes>
          <PathProbe />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await waitFor(() => expect(harness.openers.length).toBeGreaterThan(0))
    await clickLocate()

    await waitFor(() => expect(harness.path).toBe("/library/entry-1"))
  })
})
