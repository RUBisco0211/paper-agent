// @vitest-environment jsdom
import { QueryClientProvider, useQuery } from "@tanstack/react-query"
import { act, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import type { ProjectSchedule } from "@/lib/project-schedules"
import { ProjectScheduleDetail } from "./ProjectScheduleDetail"

const { request } = vi.hoisted(() => ({ request: vi.fn() }))
vi.mock("@/lib/api/provider", () => ({ useApi: () => ({ api: { client: { request } } }) }))

vi.mock("@upstream/api/schedule", () => ({ scheduleApi: { listSessions: async () => ({ sessions: [], total: 0 }) } }))

it("shows the web UI confirmation dialog before deleting a scheduled task", async () => {
  const user = userEvent.setup()
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
  const onDelete = vi.fn(async () => {})
  const task = {
    projectId: null,
    notify_email: false,
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
  const dialog = screen.getAllByRole("dialog").find((item) => item.getAttribute("data-slot") === "dialog-content")
  expect(dialog).toBeTruthy()
  expect(dialog?.querySelector('[data-slot="dialog-footer"]')).toBeTruthy()
  expect(screen.getByText("删除“问候”及全部运行记录？此操作无法撤销。")).toBeTruthy()
  expect(confirm).not.toHaveBeenCalled()
  await user.click(screen.getByRole("button", { name: "取消" }))
  expect(onDelete).not.toHaveBeenCalled()
  confirm.mockRestore()
})

it("task details update the notification binding when the user toggles email", async () => {
  request.mockResolvedValue({ schedule_id: "schedule-1", project_id: null, notify_email: true })
  const task = { projectId: null, notify_email: false, schedule: { id: "schedule-1", data: { name: "总结", cron_expression: "0 9 * * *", timezone: "UTC", enabled: true } } } as ProjectSchedule
  const queryClient = createQueryClient()
  queryClient.setQueryData(["project-schedules"], [task])
  function Details() {
    const { data } = useQuery({ queryKey: ["project-schedules"], queryFn: async () => [task], enabled: false })
    return <ProjectScheduleDetail task={data![0]} onClose={vi.fn()} onDelete={vi.fn()} />
  }
  render(<QueryClientProvider client={queryClient}><MemoryRouter><Details /></MemoryRouter></QueryClientProvider>)
  await act(async () => fireEvent.click(screen.getByRole("checkbox", { name: "邮件通知" })))
  await vi.waitFor(() => expect(screen.getByRole("checkbox", { name: "邮件通知" }).getAttribute("aria-checked")).toBe("true"))
  expect(request).toHaveBeenCalledWith("/v1/schedules/schedule-1", { method: "PATCH", json: { notify_email: true } })
})

it("task details retain the notification value when saving the toggle fails", async () => {
  request.mockRejectedValue(new Error("保存失败，请重试"))
  const task = { projectId: null, notify_email: false, schedule: { id: "schedule-2", data: { name: "总结", cron_expression: "0 9 * * *", timezone: "UTC", enabled: true } } } as ProjectSchedule
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter><ProjectScheduleDetail task={task} onClose={vi.fn()} onDelete={vi.fn()} /></MemoryRouter></QueryClientProvider>)
  await act(async () => fireEvent.click(screen.getByRole("checkbox", { name: "邮件通知" })))
  expect(screen.getByRole("checkbox", { name: "邮件通知" }).getAttribute("aria-checked")).toBe("false")
  expect(screen.getByRole("alert").textContent).toContain("保存失败")
})
