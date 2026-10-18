// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, NavLink, Route, Routes, useLocation } from "react-router-dom"
import { expect, it } from "vitest"

import { KeepAliveOutlet } from "@/components/layout/AppLayout"

function SearchPage() {
  return <input aria-label="搜索词" defaultValue="" />
}

it("keeps a sidebar route mounted when visiting another route", async () => {
  render(<MemoryRouter initialEntries={["/discover"]}>
    <NavLink to="/discover">在线检索</NavLink>
    <NavLink to="/library">文献库</NavLink>
    <Routes><Route element={<KeepAliveOutlet />}>
      <Route path="/discover" element={<SearchPage />} />
      <Route path="/library" element={<p>文献列表</p>} />
    </Route></Routes>
  </MemoryRouter>)

  await userEvent.type(screen.getByRole("textbox", { name: "搜索词" }), "agentic rag")
  await userEvent.click(screen.getByRole("link", { name: "文献库" }))
  await userEvent.click(screen.getByRole("link", { name: "在线检索" }))

  expect(screen.getByRole("textbox", { name: "搜索词" })).toHaveProperty("value", "agentic rag")
})

function ChatRoute() {
  const location = useLocation()
  return <span data-testid="chat-route">{location.pathname}</span>
}

it("keeps an inactive route bound to its own location", async () => {
  render(<MemoryRouter initialEntries={["/chat/agent/session"]}>
    <NavLink to="/library">文献库</NavLink>
    <Routes><Route element={<KeepAliveOutlet />}>
      <Route path="/chat/:agentId/:sessionId" element={<ChatRoute />} />
      <Route path="/library" element={<p>文献列表</p>} />
    </Route></Routes>
  </MemoryRouter>)

  await userEvent.click(screen.getByRole("link", { name: "文献库" }))

  expect(screen.getByTestId("chat-route").textContent).toBe("/chat/agent/session")
})
