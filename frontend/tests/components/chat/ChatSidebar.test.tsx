// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { ChatSidebar } from "@/components/chat/ChatSidebar"
import { SidebarProvider } from "@/components/ui/Sidebar"
import { TooltipProvider } from "@/components/ui/Tooltip"

const createBoundSession = vi.fn()
const boundSessions = vi.hoisted(() => ({ current: [] as Array<Record<string, unknown>> }))
vi.mock("@/components/providers/ApiProvider", () => ({ useApi: () => ({ api: { projects: { list: async () => ({ items: [] }) } } }) }))
vi.mock("@/lib/agentSessions", () => ({
  createBoundSession: (...args: unknown[]) => createBoundSession(...args),
  listBoundSessions: async () => boundSessions.current,
}))
vi.mock("@/components/projects/CreateProjectDialog", () => ({ CreateProjectDialog: () => null }))

function Path() { return <span data-testid="path">{useLocation().pathname}</span> }

it("opens a draft without creating a session when new chat is clicked", () => {
  createBoundSession.mockClear()
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={["/chat"]}><Routes>
    <Route path="/chat/*" element={<TooltipProvider><SidebarProvider><ChatSidebar /><Path /></SidebarProvider></TooltipProvider>} />
  </Routes></MemoryRouter></QueryClientProvider>)
  fireEvent.click(screen.getByRole("button", { name: "新建全局会话" }))
  expect(createBoundSession).not.toHaveBeenCalled()
  expect(screen.getByTestId("path").textContent).toBe("/chat/new")
})

function session(id: string, name: string) {
  return {
    agentId: "agent-1",
    session: { session: { id, config: { name }, created_at: "2026-10-10T00:00:00Z" } },
    binding: { project_id: null },
  }
}

it("marks the row of the open conversation as active", async () => {
  boundSessions.current = [session("session-1", "测试会话"), session("session-2", "另一个会话")]
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={["/chat/agent-1/session-1"]}><Routes>
    <Route path="/chat/*" element={<TooltipProvider><SidebarProvider><ChatSidebar /><Path /></SidebarProvider></TooltipProvider>} />
  </Routes></MemoryRouter></QueryClientProvider>)

  const open = await screen.findByRole("link", { name: "测试会话" })
  expect(open.getAttribute("data-active")).toBe("true")
  expect(screen.getByRole("link", { name: "另一个会话" }).getAttribute("data-active")).toBe("false")
})
