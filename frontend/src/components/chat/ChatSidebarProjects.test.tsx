// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { SidebarProvider } from "@/components/ui/Sidebar"
import { TooltipProvider } from "@/components/ui/Tooltip"
import { ChatSidebar } from "@/components/chat/ChatSidebar"

const state = vi.hoisted(() => ({ deleted: false }))
const project = { id: "project-1", name: "测试项目", description: null, paper_count: 0 }
const api = {
  projects: {
    list: vi.fn(async () => ({ items: state.deleted ? [] : [project], total: state.deleted ? 0 : 1 })),
    remove: vi.fn(async (_id: string) => { state.deleted = true }),
  },
}

vi.mock("@/components/providers/ApiProvider", () => ({ useApi: () => ({ api }) }))
vi.mock("@/lib/agentSessions", () => ({
  listBoundSessions: async () => [],
  deleteProjectWithSessions: async (_api: unknown, id: string) => api.projects.remove(id),
}))

it("removes the project from the conversation sidebar when a project is deleted", async () => {
  state.deleted = false
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={["/chat"]}>
        <TooltipProvider><SidebarProvider><ChatSidebar /></SidebarProvider></TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )

  expect(await screen.findByRole("button", { name: "测试项目" })).toBeTruthy()
  await userEvent.setup().click(screen.getByRole("button", { name: "测试项目操作" }))
  await userEvent.setup().click(screen.getByRole("menuitem", { name: "删除项目" }))
  await userEvent.setup().click(within(screen.getByRole("dialog", { name: "删除项目" })).getByRole("button", { name: "删除" }))

  await waitFor(() => expect(screen.queryByRole("button", { name: "测试项目" })).toBeNull())
})
