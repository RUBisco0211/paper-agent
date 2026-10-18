// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react"
import { act } from "react"
import { expect, it, vi } from "vitest"

import { ProjectScheduleDialog } from "@/components/schedule/ScheduleDialog"

it("shows the agent draft and returns edited values only after review confirmation", async () => {
  const onReview = vi.fn(async () => {})
  render(<ProjectScheduleDialog
    projects={[{ id: "project-a", name: "甲项目" }]}
    projectId="project-a"
    onProjectChange={vi.fn()}
    models={[]}
    open
    onOpenChange={vi.fn()}
    onCreate={vi.fn()}
    review={{ name: "初稿", prompt: "每天整理", time: "09:00", weekdays: ["mon", "tue", "wed", "thu", "fri"], notify_email: true }}
    onReview={onReview}
  />)
  expect(screen.getByDisplayValue("初稿")).toBeTruthy()
  expect(screen.queryByLabelText("时区")).toBeNull()
  fireEvent.change(screen.getByDisplayValue("初稿"), { target: { value: "最终任务" } })
  expect(screen.getByRole("checkbox", { name: "邮件通知" }).getAttribute("aria-checked")).toBe("true")
  fireEvent.click(screen.getByRole("checkbox", { name: "邮件通知" }))
  expect(onReview).not.toHaveBeenCalled()
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "确认创建" })))
  await vi.waitFor(() => expect(onReview).toHaveBeenCalledWith({ name: "最终任务", prompt: "每天整理", time: "09:00", weekdays: ["mon", "tue", "wed", "thu", "fri"], notify_email: false }))
})
