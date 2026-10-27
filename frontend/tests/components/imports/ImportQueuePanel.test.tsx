// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, useLocation } from "react-router-dom"
import { expect, it, vi } from "vitest"

import { createQueryClient } from "@/app/query"
import { ImportQueuePanel } from "@/components/imports/ImportQueuePanel"
import { ApiProvider } from "@/components/providers/ApiProvider"

const queue = vi.hoisted(() => ({
  setOpen: vi.fn(),
  entryId: "owned-entry-1" as string | null,
  failure: null as Record<string, unknown> | null,
}))
vi.mock("@/components/providers/ImportQueueProvider", () => ({ useImportQueue: () => ({
  open: true, setOpen: queue.setOpen, loading: false, error: false,
  items: queue.failure ? [queue.failure] : [{
    source: "download", id: "import-1", identifier: "10.1234/example",
    identifier_type: "doi", status: "success",
    paper_id: "global-paper-1", user_paper_id: queue.entryId, created_at: "2026-10-09T00:00:00Z",
    run: { status: "success", stage: "parse", error_message: null },
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

  await userEvent.click(screen.getByRole("button", { name: /DOI: 10\.1234\/example/ }))
  await userEvent.click(screen.getByRole("button", { name: "查看文献" }))

  expect(queue.setOpen).toHaveBeenCalledWith(false)
  expect(screen.getByText("文献详情抽屉 owned-entry-1")).toBeTruthy()
  expect(screen.getByTestId("path").textContent).toBe("/discover")
})

it("hides the view action when no user entry exists even though the PDF was fetched", async () => {
  queue.entryId = null
  try {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: (async () => new Response("{}")) as typeof fetch }}>
          <ImportQueuePanel />
        </ApiProvider>
      </QueryClientProvider>,
    )
    await userEvent.click(screen.getByRole("button", { name: /DOI: 10\.1234\/example/ }))
    expect(screen.queryByRole("button", { name: "查看文献" })).toBeNull()
  } finally {
    queue.entryId = "owned-entry-1"
  }
})

it("shows a failed request in the destructive tone with its reason and a retry", async () => {
  queue.entryId = null
  queue.failure = {
    source: "download",
    id: "import-failed",
    identifier: "10.1234/broken",
    identifier_type: "doi",
    status: "success",
    created_at: "2026-10-09T00:00:00Z",
    run: {
      status: "failed",
      stage: "parse",
      error_message: "解析失败：文件格式不支持",
      stage_finished_at: {},
    },
  }
  try {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: (async () => new Response("{}")) as typeof fetch }}>
          <ImportQueuePanel />
        </ApiProvider>
      </QueryClientProvider>,
    )
    const row = screen.getByRole("button", { name: /DOI: 10\.1234\/broken/ })
    // The list label is destructive, not the success tone.
    expect(row.textContent).toContain("失败")
    expect(row.querySelector(".text-success")).toBeNull()

    await userEvent.click(row)
    expect(screen.getByRole("alert").textContent).toContain("解析失败：文件格式不支持")
    expect(screen.getByRole("button", { name: "重试" })).toBeTruthy()
  } finally {
    queue.entryId = "owned-entry-1"
    queue.failure = null
  }
})

it("lists the three processing stages separately once a run exists", async () => {
  queue.entryId = null
  queue.failure = {
    source: "request",
    id: "run-2",
    identifier: "",
    identifier_type: "upload",
    status: "running",
    created_at: "2026-10-09T00:00:00Z",
    run: {
      status: "running",
      stage: "chunk",
      error_message: null,
      stage_finished_at: { parse: "2026-10-09T00:01:00Z" },
    },
  }
  try {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: (async () => new Response("{}")) as typeof fetch }}>
          <ImportQueuePanel />
        </ApiProvider>
      </QueryClientProvider>,
    )
    await userEvent.click(screen.getByRole("button", { name: /文件上传|本地上传/ }))
    const steps = screen.getAllByRole("listitem").map((node) => node.textContent)
    expect(steps).toEqual(["文件上传已完成", "解析正文已完成", "切分片段进行中", "生成向量等待"])
  } finally {
    queue.entryId = "owned-entry-1"
    queue.failure = null
  }
})

it("shows the submission time under each row so repeated identifiers differ", () => {
  queue.entryId = null
  queue.failure = {
    source: "download",
    id: "import-timed",
    identifier: "2606.24010",
    identifier_type: "arxiv",
    status: "failed",
    created_at: "2026-10-26T15:00:00Z",
    run: null,
  }
  try {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: (async () => new Response("{}")) as typeof fetch }}>
          <ImportQueuePanel />
        </ApiProvider>
      </QueryClientProvider>,
    )
    const row = screen.getByRole("button", { name: /arxiv_id: 2606\.24010/ })
    // The identifier alone cannot tell two submissions apart.
    expect(row.textContent).toMatch(/2026/)
    expect(row.textContent).toMatch(/\d{2}:\d{2}:\d{2}/)
  } finally {
    queue.entryId = "owned-entry-1"
    queue.failure = null
  }
})

it.each<[string, "doi" | "arxiv" | "upload", string]>([
  ["10.1109/tra.2026.3715346", "doi", "DOI: 10.1109/tra.2026.3715346"],
  ["2606.24010", "arxiv", "arxiv_id: 2606.24010"],
  ["a3f1c9", "upload", "file_hash: a3f1c9"],
])("names a %s request by its kind instead of a bare value", (identifier, type, title) => {
  queue.entryId = null
  queue.failure = {
    source: type === "upload" ? "request" : "download",
    id: `row-${type}`,
    identifier,
    identifier_type: type,
    status: "success",
    created_at: "2026-10-26T15:00:00Z",
    run: null,
  }
  try {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl: (async () => new Response("{}")) as typeof fetch }}>
          <ImportQueuePanel />
        </ApiProvider>
      </QueryClientProvider>,
    )
    expect(screen.getByRole("button", { name: new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })).toBeTruthy()
  } finally {
    queue.entryId = "owned-entry-1"
    queue.failure = null
  }
})
