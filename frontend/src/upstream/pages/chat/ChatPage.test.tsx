// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { ChatPage } from "./ChatPage"

vi.mock("@/lib/api/provider", () => ({ useApi: () => ({ api: {} }) }))
vi.mock("@/lib/auth/provider", () => ({ useAuth: () => ({ user: { id: "user-1" } }) }))
vi.mock("@/lib/agent-sessions", () => ({ listBoundSessions: async () => [{ agentId: "agent-1", session: { session: { id: "session-1", config: { name: "测试会话" }, created_at: "2026-10-10T00:00:00Z" } }, binding: { project_id: null } }] }))
vi.mock("@upstream/components/ui/sidebar", () => ({ SidebarProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
vi.mock("@upstream/components/ui/resizable", () => ({ ResizablePanelGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, ResizablePanel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, ResizableHandle: () => null }))
vi.mock("./ChatSidebar", () => ({ ChatSidebar: () => <aside>会话侧栏</aside> }))
vi.mock("./ProjectPapersPanel", () => ({ ProjectPapersPanel: () => <aside>项目文献</aside> }))
vi.mock("./ChatTabToolbar", () => ({ ChatTabToolbar: ({ paths, onClose, onSelect }: { paths: string[]; onClose: (path: string) => void; onSelect: (path: string) => void }) => <nav>{paths.map((path) => <span key={path}><button onClick={() => onSelect(path)}>{path}</button><button onClick={() => onClose(path)}>关闭 {path}</button></span>)}</nav> }))

function Path() {
  return <div data-testid="path">{useLocation().pathname}</div>
}

function renderChat(initialPath: string | { pathname: string; state: unknown }) {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={[initialPath]}><Routes>
    <Route path="/chat" element={<ChatPage />}>
      <Route path="new" element={<><Path />新会话页面</>} />
      <Route path=":agentId/:sessionId" element={<><Path />会话页面</>} />
    </Route>
  </Routes></MemoryRouter></QueryClientProvider>)
}

const saved = new Map<string, string>()
vi.stubGlobal("localStorage", {
  getItem: (key: string) => saved.get(key) ?? null,
  setItem: (key: string, value: string) => { saved.set(key, value) },
  clear: () => saved.clear(),
})
beforeEach(() => saved.clear())

it("restores the active session tab for the signed-in user", async () => {
  localStorage.setItem("paper-agent:chat-tabs:user-1", JSON.stringify({ paths: ["/chat/new", "/chat/agent-1/session-1"], activePath: "/chat/agent-1/session-1" }))
  renderChat("/chat")
  await waitFor(() => expect(screen.getByTestId("path").textContent).toBe("/chat/agent-1/session-1"))
})

it("shows the blank workspace after the last session tab closes", async () => {
  localStorage.setItem("paper-agent:chat-tabs:user-1", JSON.stringify({ paths: ["/chat/agent-1/session-1"], activePath: "/chat/agent-1/session-1" }))
  renderChat("/chat/agent-1/session-1")
  fireEvent.click(screen.getByRole("button", { name: "关闭 /chat/agent-1/session-1" }))
  await waitFor(() => expect(screen.queryByRole("button", { name: "/chat/agent-1/session-1" })).toBeNull())
  expect(screen.queryByRole("button", { name: "/chat/new" })).toBeNull()
  expect(screen.queryByTestId("path")).toBeNull()
})

it("replaces the draft tab after the first message creates a session", async () => {
  localStorage.setItem("paper-agent:chat-tabs:user-1", JSON.stringify({ paths: ["/chat/new"], activePath: "/chat/new" }))
  renderChat({ pathname: "/chat/agent-1/session-1", state: { replaceDraftTab: "/chat/new" } })
  await waitFor(() => expect(screen.getByRole("button", { name: "/chat/agent-1/session-1" })).toBeTruthy())
  expect(screen.queryByRole("button", { name: "/chat/new" })).toBeNull()
})

function StatefulDraft() {
  return <p>草稿页</p>
}

function StatefulSession() {
  const location = useLocation()
  return <input aria-label={location.pathname} defaultValue="" />
}

it("keeps a session input mounted when switching between tabs", async () => {
  localStorage.setItem("paper-agent:chat-tabs:user-1", JSON.stringify({ paths: ["/chat/new", "/chat/agent-1/session-1"], activePath: "/chat/agent-1/session-1" }))
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={["/chat/agent-1/session-1"]}><Routes>
    <Route path="/chat" element={<ChatPage />}>
      <Route path="new" element={<StatefulDraft />} />
      <Route path=":agentId/:sessionId" element={<StatefulSession />} />
    </Route>
  </Routes></MemoryRouter></QueryClientProvider>)
  const original = await screen.findByRole("textbox", { name: "/chat/agent-1/session-1" })
  fireEvent.change(original, { target: { value: "未发送草稿" } })
  fireEvent.click(screen.getByRole("button", { name: "/chat/new" }))
  await screen.findByText("草稿页")
  fireEvent.click(screen.getByRole("button", { name: "/chat/agent-1/session-1" }))
  expect(screen.getByRole("textbox", { name: "/chat/agent-1/session-1" })).toBe(original)
  expect(original).toHaveProperty("value", "未发送草稿")
})

it("closes the only new chat tab without opening another tab", async () => {
  localStorage.setItem("paper-agent:chat-tabs:user-1", JSON.stringify({ paths: ["/chat/new"], activePath: "/chat/new" }))
  renderChat("/chat/new")
  fireEvent.click(screen.getByRole("button", { name: "关闭 /chat/new" }))
  await waitFor(() => expect(screen.queryByRole("button", { name: "/chat/new" })).toBeNull())
  expect(screen.queryByTestId("path")).toBeNull()
})
