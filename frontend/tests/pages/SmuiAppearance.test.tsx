// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { AssistantMsg, UserMsg } from "@agentscope-ai/agentscope/message"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import type { ImportQueueItem } from "@/types/business"
import { ImportQueuePanel } from "@/components/imports/ImportQueuePanel"
import { NewChatPage } from "@/pages/chat/NewChatPage"
import { MessageNavigationRail } from "@/components/chat/MessageNavigationRail"
import { CalendarTabPage } from "@/components/schedule/CalendarTabPage"
import { ModelsSection } from "@/components/settings/ModelsSection"
import { SettingsLayout } from "@/components/settings/SettingsLayout"
import "@/i18n"

const queue = vi.hoisted(() => ({ items: [] as ImportQueueItem[] }))
vi.mock("@/components/providers/ImportQueueProvider", () => ({ useImportQueue: () => ({
  open: true, setOpen: vi.fn(), loading: false, error: false, items: queue.items,
}) }))
vi.mock("@/components/papers/PaperDetailSheet", () => ({ PaperDetailSheet: () => null }))
vi.mock("@/components/providers/ApiProvider", () => ({ useApi: () => ({ api: {
  projects: { list: async () => ({ items: [] }) },
  sessions: { llmCatalog: async () => ({ providers: [] }) },
} }) }))
vi.mock("@/lib/agentSessions", () => ({ availableChatModels: async () => [], createBoundSession: vi.fn(), sameSessionId: (left: string, right: string) => left === right }))
vi.mock("@/lib/api/agentscope/credential", () => ({ credentialApi: { list: async () => ({ credentials: [] }) } }))
vi.mock("@/components/chat/TextInput", () => ({ TextInput: ({ className }: { className: string }) => <div data-testid="composer" className={className} /> }))
vi.mock("@/components/ui/MessageScroller", () => ({
  useMessageScroller: () => ({ scrollToMessage: vi.fn() }),
  useMessageScrollerVisibility: () => ({ currentAnchorId: null, visibleMessageIds: [] }),
}))

it.each([
  ["metadata", "text-info"], ["fulltext", "text-info"],
  ["chunking", "text-info"], ["embedding", "text-info"],
  ["ready", "text-success"], ["succeeded", "text-success"],
  ["pdf_unavailable", "text-warning"],
])("the import queue uses %s semantic color when that stage is displayed", (stage, color) => {
  queue.items = [{ id: "job-1", kind: "import", title: "测试文献", status: stage, created_at: "2026-10-09T00:00:00Z" }]
  render(<ImportQueuePanel />)
  const label = screen.getByText("测试文献").parentElement!.lastElementChild!
  expect(label.classList.contains(color)).toBe(true)
})

it("the draft composer leaves surface styling to the shared input when a new conversation is opened", () => {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={["/chat/new"]}><Routes><Route element={<Outlet context={{ draftQuoteKey: "draft", draftProjectId: "", setDraftProjectId: () => {} }} />}><Route path="/chat/new" element={<NewChatPage />} /></Route></Routes></MemoryRouter></QueryClientProvider>)
  expect(screen.getByTestId("composer").className).not.toMatch(/rounded-|bg-|p-1/)
})

it("the message preview inherits the theme radius when the navigation rail expands", async () => {
  render(<MessageNavigationRail messages={[
    UserMsg({ id: "question", name: "user", content: "提问" }),
    AssistantMsg({ id: "answer", name: "assistant", content: "回答" }),
  ]} />)
  await userEvent.hover(screen.getByRole("button", { name: "跳转到第 1 条消息" }))
  const surface = screen.getByRole("navigation", { name: "会话消息导航" }).parentElement!
  expect(surface.classList.contains("rounded-lg")).toBe(true)
})

it("the calendar date inherits the theme radius when it marks today", () => {
  vi.useFakeTimers({ toFake: ["Date"] })
  vi.setSystemTime(new Date("2026-10-17T12:00:00"))
  try {
    render(<CalendarTabPage events={[]} currentDate={new Date()} onEventClick={vi.fn()} onMonthChange={vi.fn()} />)
    const marker = screen.getByText("17")
    expect(marker.classList.contains("rounded-md")).toBe(true)
  } finally {
    vi.useRealTimers()
  }
})

it("the credential form inherits the theme radius when model settings are opened", () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={["/settings/models"]}>
        <Routes>
          <Route path="/settings" element={<SettingsLayout />}>
            <Route path="models" element={<ModelsSection />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  const surface = screen.getByText("保存凭据", { selector: "h2" }).closest("section")!
  expect(surface.classList.contains("rounded-lg")).toBe(true)
})
