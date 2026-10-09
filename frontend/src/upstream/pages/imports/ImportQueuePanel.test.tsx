// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, useLocation } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { ImportQueuePanel } from "./ImportQueuePanel"

const queue = vi.hoisted(() => ({ setOpen: vi.fn() }))
vi.mock("@/lib/import-queue-context", () => ({ useImportQueue: () => ({
  open: true, setOpen: queue.setOpen, loading: false, error: false,
  items: [{ id: "job-1", kind: "import", paper_id: "paper-1", title: "测试文献", status: "running", created_at: "2026-10-09T00:00:00Z" }],
}) }))
vi.mock("@/components/papers/paper-detail-sheet", () => ({ PaperDetailSheet: ({ paperId }: { paperId: string | null }) => paperId ? <div>文献详情抽屉 {paperId}</div> : null }))

function Path() { return <span data-testid="path">{useLocation().pathname}</span> }

it("opens the paper detail drawer from the import queue without navigating", async () => {
  render(<MemoryRouter initialEntries={["/discover"]}><Path /><ImportQueuePanel /></MemoryRouter>)

  await userEvent.click(screen.getByText("测试文献"))

  expect(queue.setOpen).toHaveBeenCalledWith(false)
  expect(screen.getByText("文献详情抽屉 paper-1")).toBeTruthy()
  expect(screen.getByTestId("path").textContent).toBe("/discover")
})
