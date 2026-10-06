// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { SidebarProvider } from "@upstream/components/ui/sidebar"
import { TooltipProvider } from "@upstream/components/ui/tooltip"
import { AppSidebar } from "@upstream/components/layout/AppSidebar"
import { ProjectsPage } from "./projects"

const state = vi.hoisted(() => ({ deleted: false }))
const project = { id: "project-1", name: "测试项目", description: null, paper_count: 0 }
const api = {
  projects: {
    list: vi.fn(async () => ({ items: state.deleted ? [] : [project], total: state.deleted ? 0 : 1 })),
    remove: vi.fn(async (_id: string) => { state.deleted = true }),
  },
}

vi.mock("@/lib/api/provider", () => ({ useApi: () => ({ api }) }))
vi.mock("@/lib/auth/provider", () => ({ useAuth: () => ({ logout: vi.fn() }) }))
vi.mock("@/lib/agent-sessions", () => ({
  listBoundSessions: async () => [],
  deleteProjectWithSessions: async (_api: unknown, id: string) => api.projects.remove(id),
}))

it("removes the project from the sidebar when a project is deleted", async () => {
  state.deleted = false
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <TooltipProvider>
          <SidebarProvider>
            <AppSidebar />
            <ProjectsPage />
          </SidebarProvider>
        </TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )

  expect(await screen.findByRole("button", { name: "测试项目" })).toBeTruthy()
  await userEvent.setup().click(within(screen.getByRole("row", { name: /测试项目/ })).getByRole("button", { name: "删除" }))
  await userEvent.setup().click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "删除" }))

  await waitFor(() => expect(screen.queryByRole("button", { name: "测试项目" })).toBeNull())
})
