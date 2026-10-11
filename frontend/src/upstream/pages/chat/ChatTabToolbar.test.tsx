// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import type { BoundSession } from "@/lib/agent-sessions"
import { ChatTabToolbar } from "./ChatTabToolbar"

vi.mock("@/lib/api/provider", () => ({ useApi: () => ({ api: { projects: { list: async () => ({ items: [{ id: "project-1", name: "测试项目" }] }) } } }) }))

it("searches existing sessions from the add-tab command menu", () => {
  const onSelect = vi.fn()
  const session = { agentId: "agent-1", session: { session: { id: "session-1", config: { name: "文献讨论" }, created_at: "2026-10-10T00:00:00Z" } }, binding: { project_id: null } } as BoundSession
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter><ChatTabToolbar paths={["/chat/new"]} activePath="/chat/new" sessions={[session]} leftOpen onToggleLeft={() => {}} onSelect={onSelect} onClose={() => {}} /></MemoryRouter></QueryClientProvider>)
  fireEvent.click(screen.getByRole("button", { name: "添加会话标签" }))
  fireEvent.change(screen.getByPlaceholderText("搜索会话…"), { target: { value: "文献讨论" } })
  fireEvent.click(screen.getByText("文献讨论"))
  expect(onSelect).toHaveBeenCalledWith("/chat/agent-1/session-1")
})

it("shows the project name in a shrinkable session tab", async () => {
  const session = { agentId: "agent-1", session: { session: { id: "session-1", config: { name: "文献讨论" }, created_at: "2026-10-10T00:00:00Z" } }, binding: { project_id: "project-1" } } as BoundSession
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter><ChatTabToolbar paths={["/chat/agent-1/session-1"]} activePath="/chat/agent-1/session-1" sessions={[session]} leftOpen onToggleLeft={() => {}} onSelect={() => {}} onClose={() => {}} /></MemoryRouter></QueryClientProvider>)
  await waitFor(() => expect(screen.getByRole("tab", { name: "文献讨论 - 测试项目" })).toBeTruthy())
  expect(screen.getByRole("tab", { name: "文献讨论 - 测试项目" }).parentElement?.className).toContain("min-w-24")
})

it("keeps the add-tab control outside the scrolling tab list", () => {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter><ChatTabToolbar paths={["/chat/new"]} activePath="/chat/new" sessions={[]} leftOpen onToggleLeft={() => {}} onSelect={() => {}} onClose={() => {}} /></MemoryRouter></QueryClientProvider>)
  const add = screen.getByRole("button", { name: "添加会话标签" })
  expect(screen.getByRole("tablist").contains(add)).toBe(false)
})
