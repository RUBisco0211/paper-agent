// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import type { ProjectSchedule } from "@/lib/project-schedules"
import { ProjectScheduleDetail } from "./ProjectScheduleDetail"

vi.mock("@upstream/api/schedule", () => ({ scheduleApi: { listSessions: async () => ({ sessions: [], total: 0 }) } }))

it("shows the app confirmation dialog before deleting a scheduled task", async () => {
  const user = userEvent.setup()
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
  const onDelete = vi.fn(async () => {})
  const task = {
    projectId: null,
    schedule: {
      id: "schedule-1",
      data: {
        name: "问候",
        enabled: true,
        cron_expression: "0 10 * * *",
        started_at: "2026-10-07T00:00:00Z",
        timezone: "Asia/Shanghai",
        description: "每天问候",
      },
    },
  } as ProjectSchedule

  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter>
    <ProjectScheduleDetail task={task} onClose={vi.fn()} onDelete={onDelete} />
  </MemoryRouter></QueryClientProvider>)

  await user.click(screen.getByRole("button", { name: "删除任务" }))
  expect(screen.getByRole("alertdialog")).toBeTruthy()
  expect(screen.getByText("定时任务及全部运行记录会被删除，此操作不可撤销。")).toBeTruthy()
  expect(confirm).not.toHaveBeenCalled()
  await user.click(screen.getByRole("button", { name: "取消" }))
  expect(onDelete).not.toHaveBeenCalled()
  confirm.mockRestore()
})
