// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { PaperCalendarPage } from "@/pages/schedule/PaperCalendarPage"

vi.mock("@/components/providers/ApiProvider", () => ({ useApi: () => ({ api: { projects: { list: async () => ({ items: [], total: 0 }) } } }) }))
vi.mock("@/lib/projectSchedules", () => ({
  listProjectSchedules: async () => [{ projectId: null, notify_email: false, schedule: { id: "task-1", agent_id: "agent-1", data: { name: "问候", enabled: true, cron_expression: "0 10 * * *", started_at: "2026-10-07T00:00:00Z", timezone: "Asia/Shanghai" } } }],
}))
vi.mock("@/lib/api/agentscope/schedule", () => ({ scheduleApi: { listSessions: async () => ({ sessions: [{ id: "run-1", agent_id: "agent-1", source_schedule_id: "task-1", created_at: "2026-10-07T02:00:00", config: { name: "问候" } }], total: 1 }) } }))
vi.mock("@/pages/chat/PaperChatPage", () => ({ PaperChatPage: ({ scheduledRun }: { scheduledRun: { id: string } }) => <div>运行会话 {scheduledRun.id}</div> }))
vi.mock("@/components/schedule/CalendarTabPage", () => ({ CalendarTabPage: () => <div>日历网格</div> }))

function renderRun(path: string) {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/scheduled" element={<PaperCalendarPage />} />
    <Route path="/scheduled/:scheduleId/runs/:sessionId" element={<PaperCalendarPage />} />
  </Routes></MemoryRouter></QueryClientProvider>)
}

it("shows a run in the scheduled main area when it belongs to the task", async () => {
  renderRun("/scheduled/task-1/runs/run-1")
  expect(await screen.findByText("运行会话 run-1")).toBeTruthy()
  expect(screen.getByText("定时任务")).toBeTruthy()
  const task = screen.getByRole("button", { name: "问候" })
  expect(task.getAttribute("data-sidebar")).toBe("menu-button")
  expect(task.getAttribute("data-active")).toBe("true")
})

it("opens a scheduled conversation when its run record is clicked", async () => {
  const user = userEvent.setup()
  renderRun("/scheduled")
  await user.click(await screen.findByRole("button", { name: "问候" }))
  await user.click(await screen.findByRole("button", { name: "2026/10/07 10:00:00" }))
  expect(await screen.findByText("运行会话 run-1")).toBeTruthy()
  expect(screen.getByText("定时任务")).toBeTruthy()
})

it("does not open an unlisted run when its id is in the URL", async () => {
  renderRun("/scheduled/task-1/runs/other-run")
  expect(await screen.findByText("会话不存在")).toBeTruthy()
  expect(screen.queryByText("运行会话 other-run")).toBeNull()
})

it("shows a missing conversation when the task is not visible", async () => {
  renderRun("/scheduled/other-task/runs/run-1")
  expect(await screen.findByText("会话不存在")).toBeTruthy()
})
