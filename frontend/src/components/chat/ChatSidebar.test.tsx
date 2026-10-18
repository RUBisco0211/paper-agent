// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { ChatSidebar } from "./ChatSidebar"
import { SidebarProvider } from "@/components/ui/Sidebar"

const createBoundSession = vi.fn()
vi.mock("@/components/providers/ApiProvider", () => ({ useApi: () => ({ api: { projects: { list: async () => ({ items: [] }) } } }) }))
vi.mock("@/lib/agentSessions", () => ({
  createBoundSession: (...args: unknown[]) => createBoundSession(...args),
  listBoundSessions: async () => [],
}))
vi.mock("@/components/projects/CreateProjectDialog", () => ({ CreateProjectDialog: () => null }))

function Path() { return <span data-testid="path">{useLocation().pathname}</span> }

it("opens a draft without creating a session when new chat is clicked", () => {
  createBoundSession.mockClear()
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={["/chat"]}><Routes>
    <Route path="/chat/*" element={<SidebarProvider><ChatSidebar /><Path /></SidebarProvider>} />
  </Routes></MemoryRouter></QueryClientProvider>)
  fireEvent.click(screen.getByRole("button", { name: "新建全局会话" }))
  expect(createBoundSession).not.toHaveBeenCalled()
  expect(screen.getByTestId("path").textContent).toBe("/chat/new")
})
