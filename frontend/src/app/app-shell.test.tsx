// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { AppShell } from "@/app/app-shell"
import { createQueryClient } from "@/app/query"
import { ApiProvider } from "@/lib/api/provider"
import { AuthProvider } from "@/lib/auth/provider"

const PROJECT = {
  id: "proj-1",
  name: "阅读清单",
  description: null,
  paper_count: 1,
  created_at: "2026-09-17T00:00:00Z",
  updated_at: "2026-09-17T00:00:00Z",
}

const SESSION = {
  id: "sess-1",
  title: "已有会话",
  scope: "project",
  project_id: "proj-1",
  paper_id: null,
  pending: { steering: 0, follow_up: 0 },
  created_at: "2026-09-17T00:00:00Z",
  updated_at: "2026-09-17T00:00:00Z",
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname + location.search}</div>
}

function renderShell(fetchImpl: typeof fetch, entries: string[] = ["/library"]) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <ApiProvider options={{ baseUrl: "http://api.test", fetchImpl }}>
        <AuthProvider>
          <MemoryRouter initialEntries={entries}>
            <Routes>
              <Route path="*" element={<AppShell />} />
            </Routes>
            <LocationProbe />
          </MemoryRouter>
        </AuthProvider>
      </ApiProvider>
    </QueryClientProvider>,
  )
}

function makeFetch(overrides: { onSessionCreate?: (body: unknown) => void } = {}) {
  return vi.fn(async (input: string | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith("/v1/auth/refresh")) {
      return json({
        access_token: "token-1",
        token_type: "bearer",
        expires_in: 900,
        expires_at: new Date(Date.now() + 900_000).toISOString(),
      })
    }
    if (url.endsWith("/v1/auth/me")) {
      return json({
        id: "u1",
        email: "reader@example.com",
        display_name: "Reader",
        created_at: "2026-09-17T00:00:00Z",
      })
    }
    if (url.includes("/v1/projects")) {
      return json({ items: [PROJECT], total: 1, limit: 10, offset: 0 })
    }
    if (url.endsWith("/v1/sessions") && init?.method === "POST") {
      overrides.onSessionCreate?.(JSON.parse(String(init.body)))
      return json(SESSION, 201)
    }
    if (url.includes("/v1/sessions")) {
      return json({ items: [SESSION], total: 1, limit: 8, offset: 0 })
    }
    return json({ items: [], total: 0, limit: 200, offset: 0 })
  })
}

async function openProjectMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "阅读清单 操作" }))
}

describe("AppShell sidebar", () => {
  it("groups sessions and exposes project actions that are wired up", async () => {
    const user = userEvent.setup()
    const onSessionCreate = vi.fn()
    renderShell(makeFetch({ onSessionCreate }) as unknown as typeof fetch)

    // 分组与全局分组都在，且有会话链接
    expect(await screen.findByText("全局")).toBeTruthy()
    expect(await screen.findByText("已有会话")).toBeTruthy()

    await openProjectMenu(user)

    expect(screen.getByRole("menuitem", { name: /查看详情/ })).toBeTruthy()
    expect(screen.getByRole("menuitem", { name: /添加文献/ })).toBeTruthy()
    expect(screen.getByRole("menuitem", { name: /新建会话/ })).toBeTruthy()
    expect(screen.getByRole("menuitem", { name: /删除项目/ })).toBeTruthy()

    // 新建会话：真的创建了项目会话
    await user.click(screen.getByRole("menuitem", { name: /新建会话/ }))
    await waitFor(() => expect(onSessionCreate).toHaveBeenCalledTimes(1))
    expect(onSessionCreate.mock.calls[0][0]).toMatchObject({ project_id: "proj-1" })
  })

  it("routes 查看详情 and 添加文献 to the project page", async () => {
    const user = userEvent.setup()
    renderShell(makeFetch() as unknown as typeof fetch)

    await openProjectMenu(user)
    await user.click(screen.getByRole("menuitem", { name: /查看详情/ }))
    expect(screen.getByTestId("location").textContent).toBe("/projects/proj-1")

    await openProjectMenu(user)
    await user.click(screen.getByRole("menuitem", { name: /添加文献/ }))
    expect(screen.getByTestId("location").textContent).toBe("/projects/proj-1?add=1")
  })

  it("asks for confirmation before deleting a project", async () => {
    const user = userEvent.setup()
    renderShell(makeFetch() as unknown as typeof fetch)

    await openProjectMenu(user)
    await user.click(screen.getByRole("menuitem", { name: /删除项目/ }))

    expect(
      await screen.findByText("删除项目「阅读清单」？"),
    ).toBeTruthy()
    expect(screen.getByText(/项目中的会话会一并删除/)).toBeTruthy()
  })

  it("collapses a group when its row is clicked", async () => {
    const user = userEvent.setup()
    renderShell(makeFetch() as unknown as typeof fetch)

    // 项目分组默认折叠；展开状态对辅助技术可见
    // （jsdom 不触发动画结束，因此断言状态而不是断言子项被卸载）
    const row = await screen.findByRole("button", { name: "阅读清单" })
    expect(row.getAttribute("aria-expanded")).toBe("false")

    await user.click(row)

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "阅读清单" }).getAttribute("aria-expanded"),
      ).toBe("true"),
    )
  })
})


describe("AppShell active navigation", () => {
  async function activeState(entries: string[]) {
    renderShell(makeFetch() as unknown as typeof fetch, entries)
    const library = (await screen.findByRole("link", { name: /文献库/ })).getAttribute(
      "data-active",
    )
    const projects = (await screen.findByRole("link", { name: /^项目$/ })).getAttribute(
      "data-active",
    )
    const settings = (await screen.findByRole("link", { name: /设置/ })).getAttribute(
      "data-active",
    )
    return { library, projects, settings }
  }

  it("marks the current section and only that one", async () => {
    // 激活项靠 data-active 生效（组件用 data-[active=true] 上背景色）
    expect(await activeState(["/library"])).toEqual({
      library: "true",
      projects: "false",
      settings: "false",
    })
  })

  it("keeps a section active on its sub-pages", async () => {
    expect(await activeState(["/projects/proj-1"])).toEqual({
      library: "false",
      projects: "true",
      settings: "false",
    })
  })
})
