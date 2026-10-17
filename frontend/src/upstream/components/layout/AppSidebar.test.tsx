// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, useLocation } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { SidebarProvider } from "@upstream/components/ui/sidebar"
import { TooltipProvider } from "@upstream/components/ui/tooltip"
import { AppSidebar } from "./AppSidebar"

vi.mock("@/lib/auth/provider", () => ({ useAuth: () => ({ user: { email: "reader@example.com" }, logout: vi.fn() }) }))
vi.mock("@/lib/import-queue-context", () => ({ useImportQueue: () => ({ setOpen: vi.fn(), active: false }) }))
vi.mock("@upstream/pages/imports/ImportQueuePanel", () => ({ ImportQueuePanel: () => null }))

function Path() { return <span data-testid="path">{useLocation().pathname}</span> }

it("returns to the last visited chat route after switching sidebar sections", async () => {
  render(<MemoryRouter initialEntries={["/chat/agent/session"]}>
    <TooltipProvider><SidebarProvider><AppSidebar /><Path /></SidebarProvider></TooltipProvider>
  </MemoryRouter>)

  await userEvent.click(screen.getByRole("link", { name: "文献库" }))
  await userEvent.click(screen.getByRole("link", { name: "对话" }))

  expect(screen.getByTestId("path").textContent).toBe("/chat/agent/session")
})

it("opens password reset from the account menu when the user selects it", async () => {
  render(<MemoryRouter initialEntries={["/library"]}>
    <TooltipProvider><SidebarProvider><AppSidebar /><Path /></SidebarProvider></TooltipProvider>
  </MemoryRouter>)

  await userEvent.click(screen.getByRole("button", { name: "账户" }))
  await userEvent.click(await screen.findByRole("menuitem", { name: /重置密码/ }))

  expect(screen.getByTestId("path").textContent).toBe("/password-reset")
})
