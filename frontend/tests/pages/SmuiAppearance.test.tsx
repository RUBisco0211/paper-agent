// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { AssistantMsg, UserMsg } from "@agentscope-ai/agentscope/message"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import type { DownloadStatus, ImportQueueItem, RunStatus } from "@/types/business"
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

it.each<[DownloadStatus, RunStatus | null, string]>([
  ["pending", null, "等待中"],
  ["running", null, "处理中"],
  ["success", "running", "处理中"],
  ["success", "success", "已完成"],
  ["failed", null, "失败"],
])('the import queue list reads a %s request with a %s run as one state', (status, runStatus, label) => {
  queue.items = [{
    source: "download",
    id: "import-1",
    identifier: "10.1234/example",
    identifier_type: "doi",
    status,
    created_at: "2026-10-09T00:00:00Z",
    run: runStatus ? { status: runStatus, stage: "parse", error_message: null } : null,
  }]
  render(
    <QueryClientProvider client={createQueryClient()}>
      <ImportQueuePanel />
    </QueryClientProvider>,
  )
  expect(screen.getByText(label)).toBeTruthy()
})

it("the import queue lists no steps until the request is opened", () => {
  queue.items = [{
    source: "download",
    id: "import-2",
    identifier: "10.1234/example",
    identifier_type: "doi",
    status: "success",
    created_at: "2026-10-09T00:00:00Z",
    run: { status: "running", stage: "chunk", error_message: null },
  }]
  render(
    <QueryClientProvider client={createQueryClient()}>
      <ImportQueuePanel />
    </QueryClientProvider>,
  )
  // The list only reports state; which steps ran is a detail of the request.
  expect(screen.queryByText("获取原文")).toBeNull()
  expect(screen.queryByText("切分片段")).toBeNull()
})

it("an upload shows its own first step, since it never fetched anything", async () => {
  queue.items = [{
    source: "request",
    id: "run-1",
    identifier: "",
    identifier_type: "upload",
    status: "running",
    created_at: "2026-10-09T00:00:00Z",
    run: { status: "running", stage: "parse", error_message: null },
  }]
  render(
    <QueryClientProvider client={createQueryClient()}>
      <ImportQueuePanel />
    </QueryClientProvider>,
  )
  await userEvent.click(screen.getByRole("button", { name: /本地上传/ }))
  expect(screen.getByText("文件上传")).toBeTruthy()
  expect(screen.getByText("解析正文")).toBeTruthy()
  expect(screen.queryByText("获取原文")).toBeNull()
})

it("a failed fetch reports its reason instead of a processing step", async () => {
  queue.items = [{
    source: "download",
    id: "import-3",
    identifier: "10.1234/missing",
    identifier_type: "doi",
    status: "failed",
    error_message: "没有找到可用的原文",
    created_at: "2026-10-09T00:00:00Z",
    run: null,
  }]
  render(
    <QueryClientProvider client={createQueryClient()}>
      <ImportQueuePanel />
    </QueryClientProvider>,
  )
  await userEvent.click(screen.getByRole("button", { name: /10.1234\/missing/ }))
  expect(screen.getByText("没有找到可用的原文")).toBeTruthy()
  expect(screen.queryByText("生成向量")).toBeNull()
})

it("the draft composer leaves surface styling to the shared input when a new conversation is opened", () => {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={["/chat/new"]}><Routes><Route element={<Outlet context={{ draftQuoteKey: "draft", draftProjectId: "", setDraftProjectId: () => {} }} />}><Route path="/chat/new" element={<NewChatPage />} /></Route></Routes></MemoryRouter></QueryClientProvider>)
  expect(screen.getByTestId("composer").className).not.toMatch(/rounded-|bg-|p-1/)
})

it("the message preview inherits the theme radius when the navigation rail expands", async () => {
  render(<MessageNavigationRail messages={[
    UserMsg({ id: "question", name: "user", content: "提问" }),
    AssistantMsg({ id: "answer", name: "assistant", content: "回答" }),
    UserMsg({ id: "question-2", name: "user", content: "追问" }),
  ]} />)
  await userEvent.hover(screen.getByRole("button", { name: "跳转到第 1 个提问" }))
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
