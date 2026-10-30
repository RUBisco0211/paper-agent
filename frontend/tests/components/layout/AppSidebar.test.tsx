// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, useLocation } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { ChatSidebarProvider, useChatSidebarVisibility } from "@/components/providers/ChatSidebarProvider"
import { SidebarProvider } from "@/components/ui/Sidebar"
import { TooltipProvider } from "@/components/ui/Tooltip"
import { AppSidebar } from "@/components/layout/AppSidebar"

vi.mock("@/components/providers/AuthProvider", () => ({ useAuth: () => ({ user: { email: "reader@example.com" }, logout: vi.fn() }) }))
vi.mock("@/components/providers/ImportQueueProvider", () => ({ useImportQueue: () => ({ setOpen: vi.fn(), active: false }) }))
vi.mock("@/components/imports/ImportQueuePanel", () => ({ ImportQueuePanel: () => null }))

function Path() { return <span data-testid="path">{useLocation().pathname}</span> }

it("returns to the last visited chat route after switching sidebar sections", async () => {
  render(<MemoryRouter initialEntries={["/chat/agent/session"]}>
    <TooltipProvider><SidebarProvider><AppSidebar /><Path /></SidebarProvider></TooltipProvider>
  </MemoryRouter>)

  await userEvent.click(screen.getByRole("link", { name: "文献库" }))
  await userEvent.click(screen.getByRole("link", { name: "对话" }))

  expect(screen.getByTestId("path").textContent).toBe("/chat/agent/session")
})

function Probe() {
  const { open } = useChatSidebarVisibility()
  return <span data-testid="chat-sidebar">{open ? "open" : "closed"}</span>
}

function renderRail(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <TooltipProvider><SidebarProvider>
        <ChatSidebarProvider><AppSidebar /><Probe /></ChatSidebarProvider>
      </SidebarProvider></TooltipProvider>
    </MemoryRouter>,
  )
}

it("folds the conversation sidebar from the rail button instead of navigating", async () => {
  renderRail("/chat/agent-1/session-1")

  await userEvent.click(screen.getByRole("button", { name: "收起会话侧栏" }))

  expect(screen.getByTestId("chat-sidebar").textContent).toBe("closed")
  expect(screen.getByRole("button", { name: "展开会话侧栏" })).toBeTruthy()
})

it("keeps the conversation entry as a link outside a conversation", () => {
  renderRail("/library")

  expect(screen.getByRole("link", { name: "对话" })).toBeTruthy()
  expect(screen.queryByRole("button", { name: "收起会话侧栏" })).toBeNull()
})
