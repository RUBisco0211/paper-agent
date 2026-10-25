// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, useLocation } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { ImportQueuePanel } from "@/components/imports/ImportQueuePanel"
import { ApiProvider } from "@/components/providers/ApiProvider"

const queue = vi.hoisted(() => ({ setOpen: vi.fn() }))
vi.mock("@/components/providers/ImportQueueProvider", () => ({ useImportQueue: () => ({
  open: true, setOpen: queue.setOpen, loading: false, error: false,
  items: [{
    id: "import-1", identifier: "10.1234/example", identifier_type: "doi",
    paper_id: "paper-1", title: "测试文献", status: "running",
    created_at: "2026-10-09T00:00:00Z", stages: [],
  }],
}) }))
vi.mock("@/components/papers/PaperDetailSheet", () => ({ PaperDetailSheet: ({ paperId }: { paperId: string | null }) => paperId ? <div>文献详情抽屉 {paperId}</div> : null }))

function Path() { return <span data-testid="path">{useLocation().pathname}</span> }

it("opens the paper detail drawer from the import queue without navigating", async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: (async () => new Response("{}")) as typeof fetch }}>
        <MemoryRouter initialEntries={["/discover"]}>
          <Path />
          <ImportQueuePanel />
        </MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>,
  )

  await userEvent.click(screen.getByText("测试文献"))

  expect(queue.setOpen).toHaveBeenCalledWith(false)
  expect(screen.getByText("文献详情抽屉 paper-1")).toBeTruthy()
  expect(screen.getByTestId("path").textContent).toBe("/discover")
})
