// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { PaperCalendarPage } from "./PaperCalendarPage"

vi.mock("@/lib/api/provider", () => ({ useApi: () => ({ api: { projects: { list: async () => ({ items: [
  { id: "project-a", name: "甲项目" },
  { id: "project-b", name: "乙项目" },
], total: 2 }) } } }) }))
vi.mock("./calendar-tab-page", () => ({ CalendarTabPage: () => <div>日历网格</div> }))

it("groups the calendar task sidebar by project when no tasks exist", async () => {
  render(<QueryClientProvider client={createQueryClient()}><PaperCalendarPage /></QueryClientProvider>)
  expect(await screen.findByText("甲项目")).toBeTruthy()
  expect(screen.getByText("乙项目")).toBeTruthy()
  expect(screen.getAllByText("暂无定时任务")).toHaveLength(2)
})
